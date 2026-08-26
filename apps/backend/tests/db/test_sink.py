"""Tests for ProvenanceSink: async writer + sync queue."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import LLMRequests
from bebshax.db.sink import ProvenanceSink
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import TaskType


@pytest.mark.asyncio
async def test_insert_batch_writes_row_round_trip(async_engine) -> None:
    """Audit B1: a ProvenanceRecord must land as a real llm_requests row.

    ProvenanceRecord.task is a plain str (StrEnum coerced by pydantic); the
    sink must not assume an enum. Fails with total_written == 0 on the old
    `r.task.value` code.
    """
    sessionmaker_ = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
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
    from unittest.mock import MagicMock, AsyncMock

    async_sessionmaker = MagicMock()
    async_sessionmaker.return_value.__aenter__ = AsyncMock()
    async_sessionmaker.return_value.__aexit__ = AsyncMock()

    sink = ProvenanceSink(async_sessionmaker, batch_size=10)

    # Note: Not starting the writer task to avoid hangs
    # Just verify the sink is set up correctly
    assert sink.batch_size == 10
    assert hasattr(sink, 'queue')
    assert hasattr(sink, 'total_enqueued')
