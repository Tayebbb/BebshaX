import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from bebshax.db import capacity_state
from bebshax.db.sink import ProvenanceSink
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord, ProviderObservation
from bebshax.llm.quota import QuotaLedger


def _maker(rows=()):
    session = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.execute.return_value.scalars.return_value.all.return_value = list(rows)
    session.execute.return_value.all.return_value = list(rows)
    session.get_bind.return_value.dialect.name = "postgresql"
    maker = MagicMock()
    maker.return_value.__aenter__ = AsyncMock(return_value=session)
    maker.return_value.__aexit__ = AsyncMock(return_value=False)
    return maker, session


def _record():
    return ProvenanceRecord(
        request_id="runtime-durable-record", task="PERSONA_RESPONSE", pool="conversation",
        attempts=[AttemptRecord(
            attempt_number=1, provider="freellmpool", model="auto", elapsed_ms=850,
            observations=[
                ProviderObservation(provider="groq", requested_model="requested", reported_model="reported",
                                    outcome="succeeded", consumption="known", latency_ms=25,
                                    input_tokens=10, output_tokens=20),
                ProviderObservation(provider="cerebras", requested_model="failed", outcome="aborted",
                                    consumption="unknown"),
                ProviderObservation(provider="groq", requested_model="cached", outcome="cached",
                                    consumption="none"),
            ],
        )],
    )


async def test_durable_sink_acknowledges_only_after_commit():
    maker, session = _maker()
    entered, release = asyncio.Event(), asyncio.Event()

    async def commit():
        entered.set()
        await release.wait()

    session.commit.side_effect = commit
    sink, record = ProvenanceSink(maker), _record()
    task = asyncio.create_task(sink.persist(record))
    await entered.wait()
    assert record.persistence_status == "submitted"
    assert not task.done()
    release.set()
    await task
    assert record.persistence_status == "acknowledged"
    assert sink.total_written == 1
    stored = session.add_all.call_args.args[0][0]
    assert stored.attempts[0]["observations"][0]["requested_model"] == "requested"
    assert stored.attempts[0]["elapsed_ms"] == 850


async def test_durable_sink_retains_failed_record_and_redacts_driver_error(caplog):
    maker, session = _maker()
    session.commit.side_effect = RuntimeError("private-driver-payload")
    sink, record = ProvenanceSink(maker), _record()
    with pytest.raises(RuntimeError, match="Provenance persistence failed") as failure:
        await sink.persist(record)
    assert record.persistence_status == "failed"
    assert sink.failed_records[record.request_id] is record
    assert sink.total_written == 0
    assert "private-driver-payload" not in caplog.text
    assert "private-driver-payload" not in str(failure.value)


async def test_durable_sink_cancellation_remains_unknown_and_retains_provenance():
    maker, session = _maker()
    session.commit.side_effect = asyncio.CancelledError()
    sink, record = ProvenanceSink(maker), _record()
    with pytest.raises(asyncio.CancelledError):
        await sink.persist(record)
    assert record.persistence_status == "unknown"
    assert sink.failed_records[record.request_id] is record


async def test_cooldown_upsert_uses_atomic_max_and_drain_waits():
    maker, session = _maker()
    store = capacity_state.CooldownStore(maker)
    store.persist("groq", "*", 180)
    await store.drain()
    statement = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (provider_name, model_name) DO UPDATE" in statement
    assert "CASE" in statement or "greatest(" in statement
    assert "model_registry.cooldown_until" in statement
    assert "excluded.cooldown_until" in statement
    assert store.pending_count == 0
    session.commit.assert_awaited_once()
    await store.aclose()


async def test_cooldown_restore_failure_is_not_reported_as_empty():
    maker, session = _maker()
    session.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        await capacity_state.CooldownStore(maker).load_active()


async def test_cooldown_close_waits_for_commit_and_refuses_new_writes() -> None:
    maker, session = _maker()
    entered, release = asyncio.Event(), asyncio.Event()

    async def commit() -> None:
        entered.set()
        await release.wait()

    session.commit.side_effect = commit
    store = capacity_state.CooldownStore(maker)
    store.persist("groq", "*", 180)
    await asyncio.wait_for(entered.wait(), timeout=1)
    closing = asyncio.create_task(store.aclose())
    try:
        await asyncio.sleep(0)
        assert not closing.done()
        assert store.pending_count == 1
        with pytest.raises(RuntimeError, match="closed"):
            store.persist("groq", "*", 360)
    finally:
        release.set()
        await asyncio.wait_for(closing, timeout=1)
    assert store.pending_count == 0
    assert store.failed_writes == 0


async def test_cooldown_finalization_surfaces_failed_commit_without_driver_payload(caplog) -> None:
    maker, session = _maker()
    session.commit.side_effect = RuntimeError("private-cooldown-driver-payload")
    store = capacity_state.CooldownStore(maker)
    store.persist("groq", "*", 180)

    with pytest.raises(RuntimeError, match="Cooldown persistence failed") as failure:
        await asyncio.wait_for(store.aclose(), timeout=1)

    assert store.pending_count == 0
    assert store.failed_writes == 1
    assert "private-cooldown-driver-payload" not in caplog.text
    assert "private-cooldown-driver-payload" not in str(failure.value)


async def test_daily_replay_preserves_failed_cached_and_unknown_attempts():
    record = _record()
    row = SimpleNamespace(
        request_id=record.request_id, task=record.task, pool=record.pool,
        owner_id="runtime-owner", persona_id=None, conversation_id=None,
        created_at=record.created_at.replace(tzinfo=None),
        study_id=None, data_classification="unknown", processing_policy_id=None,
        processing_provider_allowlist=[], processing_openrouter_upstreams=[], estimated_tokens=None,
        routing_path=[], attempts=[attempt.model_dump(mode="json") for attempt in record.attempts],
        served_by_provider=None, response_model=None, request_model=None,
        input_tokens=None, output_tokens=None, total_latency_ms=900, success=False,
    )
    maker, session = _maker([row])
    records = await capacity_state.load_todays_provenance(maker)
    ledger = QuotaLedger()
    ledger.seed_provenance(records)
    ledger.seed_provenance(records)
    assert ledger.used_today("groq") == (1, 30)
    assert ledger.used_today("cerebras") == (1, 0)
    summary = {entry["provider"]: entry for entry in ledger.snapshot()}
    assert summary["groq"]["cached_today"] == 1
    assert summary["cerebras"]["aborted_today"] == 1
    assert summary["cerebras"]["unknown_consumption_today"] == 1
    assert records[0].owner_user_id == "runtime-owner"
    assert records[0].created_at.tzinfo == timezone.utc
    assert "success IS true" not in str(session.execute.call_args.args[0])


async def test_latency_replay_uses_inner_requested_target_not_outer_elapsed():
    attempt = _record().attempts[0].model_dump(mode="json")
    attempt.update(success=True, latency_ms=8000, via="freellmpool/auto")
    attempt["observations"].extend([
        ProviderObservation(provider="openrouter", requested_model="secondary", outcome="succeeded",
                            consumption="known", latency_ms=100).model_dump(mode="json"),
        ProviderObservation(provider="groq", requested_model="unknown", outcome="unknown",
                            consumption="unknown", latency_ms=100).model_dump(mode="json"),
    ])
    maker, _ = _maker([(datetime.now(timezone.utc), [attempt])])
    assert await capacity_state.load_recent_route_observations(maker) == [("groq", "requested", 25.0)]


async def test_sink_captures_owner_before_queued_task_leaves_request_scope():
    from bebshax.tenancy_context import tenant_scope

    maker, session = _maker()
    sink, record = ProvenanceSink(maker, batch_size=1), _record()
    with tenant_scope("runtime-owner"):
        sink(record)
    with tenant_scope("different-task-owner"):
        await sink.start()
        await sink.stop()
    assert session.add_all.call_args.args[0][0].owner_id == "runtime-owner"


async def test_durable_sink_uses_verified_request_owner():
    from bebshax.tenancy_context import tenant_scope

    maker, session = _maker()
    sink, record = ProvenanceSink(maker), _record()
    with tenant_scope("runtime-owner"):
        await sink.persist(record)
    assert session.add_all.call_args.args[0][0].owner_id == "runtime-owner"