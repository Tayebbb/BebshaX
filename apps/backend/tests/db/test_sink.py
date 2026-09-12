"""Tests for ProvenanceSink: async writer + sync queue."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from bebshax.db.models import LLMRequests
from bebshax.db.sink import ProvenanceSink
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.provenance import ProviderObservation
from bebshax.llm.types import TaskType


@pytest.mark.asyncio
async def test_insert_batch_writes_row_round_trip(async_engine) -> None:
    """Audit B1: a ProvenanceRecord must land as a real llm_requests row.

    ProvenanceRecord.task is a plain str (StrEnum coerced by pydantic); the
    sink must not assume an enum. Fails with total_written == 0 on the old
    `r.task.value` code.
    """
    sessionmaker_ = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(sessionmaker_)
    record = ProvenanceRecord(
        request_id="req_b1_roundtrip",
        task=TaskType.PERSONA_GENERATION,  # pydantic stores this as str
        pool="reasoning",
        success=True,
        input_tokens=10,
        output_tokens=20,
        # attempts carry datetimes — exercises JSON-safe serialization too
        attempts=[AttemptRecord(attempt_number=1, provider="fake", model="m", success=True)],
    )
    assert isinstance(record.task, str) and not hasattr(record.task, "value")

    await sink._insert_batch([record])

    assert sink.total_written == 1
    assert sink.total_db_errors == 0
    assert sink.total_dropped == 0
    async with sessionmaker_() as session:
        rows = (await session.execute(select(LLMRequests))).scalars().all()
    assert len(rows) == 1
    assert rows[0].request_id == "req_b1_roundtrip"
    assert rows[0].task == "PERSONA_GENERATION"


@pytest.mark.asyncio
async def test_writer_survives_idle_timeouts_and_keeps_writing(async_engine) -> None:
    """Live 2026-08-26 finding: an idle wait_for timeout was treated as the
    shutdown sentinel — the writer died ~5s after startup and every record
    enqueued afterwards was silently dropped. This test idles the writer,
    then enqueues, and requires the row to land.
    """
    sessionmaker_ = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(sessionmaker_, batch_timeout_ms=30)
    await sink.start()
    try:
        await asyncio.sleep(0.15)  # several idle ticks — the old writer is dead by now
        sink(
            ProvenanceRecord(
                request_id="req_after_idle",
                task=TaskType.PERSONA_INTERVIEW,
                pool="conversation",
                success=True,
            )
        )
        await asyncio.wait_for(sink.flush(), timeout=5)
    finally:
        await sink.stop()
    assert sink.total_written == 1
    assert sink.total_dropped == 0
    async with sessionmaker_() as session:
        rows = (await session.execute(select(LLMRequests))).scalars().all()
    assert [r.request_id for r in rows] == ["req_after_idle"]


def test_sink_creation() -> None:
    """Test that sink can be instantiated."""
    from unittest.mock import MagicMock

    async_sessionmaker = MagicMock()
    sink = ProvenanceSink(async_sessionmaker)

    assert sink is not None
    assert sink.total_enqueued == 0
    assert sink.total_written == 0


def test_sink_enqueue_sync_no_raise() -> None:
    """Test that sink.__call__ never raises, even when not started."""
    from unittest.mock import MagicMock

    async_sessionmaker = MagicMock()
    sink = ProvenanceSink(async_sessionmaker, batch_size=10)

    record = ProvenanceRecord(
        request_id="test_001",
        task=TaskType.PERSONA_GENERATION,
        attempts=[],
        success=True,
    )

    # Should not raise even though sink is not started
    try:
        sink(record)
        # If started, increment counter
        assert sink.total_enqueued >= 0
    except Exception as e:
        pytest.fail(f"sink.__call__ should never raise, but raised {e}")


@pytest.mark.asyncio
async def test_sink_queue_full_counter() -> None:
    """Test that queue full increments counter without raising."""
    from unittest.mock import MagicMock

    maker = MagicMock()
    sink = ProvenanceSink(maker, batch_size=10)
    for index in range(sink.queue.maxsize):
        sink(ProvenanceRecord(request_id=f"queued-{index}", task=TaskType.PERSONA_RESPONSE))
    overflow = ProvenanceRecord(request_id="overflow", task=TaskType.PERSONA_RESPONSE)

    sink(overflow)

    assert sink.queue.full()
    assert sink.total_enqueued == sink.queue.maxsize
    assert sink.queue_full_count == 1
    assert sink.total_dropped == 1
    assert sink.total_written == 0
    assert sink.failed_records[overflow.request_id] is overflow
    assert overflow.persistence_status == "failed"
    maker.assert_not_called()
    await sink.stop()
    assert sink.queue.empty()
    assert sink.total_dropped == sink.queue.maxsize + 1


async def test_persist_acknowledges_sqlite_commit_with_complete_attempts(async_engine):
    from bebshax.tenancy_context import tenant_scope

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(maker)
    record = ProvenanceRecord(
        request_id="durable-sqlite", task=TaskType.PERSONA_RESPONSE, success=False,
        attempts=[AttemptRecord(
            attempt_number=1, provider="freellmpool", model="auto", elapsed_ms=400,
            observations=[ProviderObservation(
                provider="groq", requested_model="requested", reported_model="reported",
                outcome="aborted", consumption="unknown", latency_ms=None,
            )],
        )],
    )
    with tenant_scope("sink-test-owner"):
        await sink.persist(record)
    assert record.persistence_status == "acknowledged"
    async with maker() as session:
        row = await session.get(LLMRequests, record.request_id)
    assert row is not None
    assert row.owner_id == "sink-test-owner"
    assert row.attempts == [attempt.model_dump(mode="json") for attempt in record.attempts]
    assert row.success is False
    assert sink.total_written == 1
    assert sink.failed_records == {}


async def test_persist_preserves_explicit_request_owner_without_context(async_engine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(maker)
    record = ProvenanceRecord(
        request_id="explicit-owner", task=TaskType.PERSONA_RESPONSE,
        owner_user_id="verified-request-owner",
    )

    await sink.persist(record)

    async with maker() as session:
        row = await session.get(LLMRequests, record.request_id)
    assert row is not None
    assert row.owner_id == "verified-request-owner"
    assert record.persistence_status == "acknowledged"


async def test_persist_rejects_conflicting_explicit_request_owner(async_engine) -> None:
    from bebshax.tenancy_context import tenant_scope

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(maker)
    record = ProvenanceRecord(
        request_id="conflicting-owner", task=TaskType.PERSONA_RESPONSE,
        owner_user_id="different-request-owner",
    )

    with tenant_scope("verified-request-owner"):
        with pytest.raises(RuntimeError, match="Provenance persistence failed"):
            await sink.persist(record)

    assert record.persistence_status == "failed"
    assert sink.failed_records[record.request_id] is record
    assert sink.total_written == 0
    async with maker() as session:
        assert await session.get(LLMRequests, record.request_id) is None


async def test_durable_replay_preserves_policy_context_and_account_observations(async_engine) -> None:
    from bebshax.db.capacity_state import load_todays_provenance
    from bebshax.llm.quota import QuotaLedger

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    ledger = QuotaLedger()
    reservation = ledger.reserve_attempt("groq")
    record = ProvenanceRecord(
        request_id="complete-durable-context", task=TaskType.PERSONA_RESPONSE,
        owner_user_id="verified-request-owner", study_id="original-study",
        data_classification="private", processing_policy_id="approved-policy-v1",
        processing_provider_allowlist=("groq", "cerebras"),
        processing_openrouter_upstreams=("approved-upstream",), estimated_tokens=1200,
        attempts=[AttemptRecord(
            attempt_number=1, provider="freellmpool", model="auto", elapsed_ms=850,
            observations=[
                ProviderObservation(
                    provider="groq", requested_model="requested", reported_model="reported",
                    account_reservation_id=reservation, outcome="succeeded", consumption="known",
                    input_tokens=10, output_tokens=20, latency_ms=25,
                ),
                ProviderObservation(
                    provider="cerebras", requested_model="failed", outcome="aborted", consumption="unknown",
                ),
                ProviderObservation(
                    provider="groq", requested_model="cached", outcome="cached", consumption="none",
                ),
            ],
        )],
    )

    await ProvenanceSink(maker).persist(record)
    ledger.record(record)
    restored = await load_todays_provenance(maker)

    assert len(restored) == 1
    preserved_fields = {
        "owner_user_id", "study_id", "data_classification", "processing_policy_id",
        "processing_provider_allowlist", "processing_openrouter_upstreams", "estimated_tokens", "attempts",
    }
    assert restored[0].model_dump(include=preserved_fields) == record.model_dump(include=preserved_fields)
    restarted = QuotaLedger()
    restarted.seed_provenance(restored)
    restarted.seed_provenance(restored)
    assert restarted.used_today("groq") == (1, 30)
    assert restarted.used_today("cerebras") == (1, 0)
    assert restarted.snapshot() == ledger.snapshot()
