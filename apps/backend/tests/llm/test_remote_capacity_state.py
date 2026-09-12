import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.capacity_state import CooldownStore, load_todays_consumption, load_todays_provenance
from bebshax.db.models import LLMRequests, ModelRegistry
from bebshax.llm.types import TaskType


@pytest.fixture
async def capacity_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'capacity.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ModelRegistry.__table__.create)
        await connection.run_sync(LLMRequests.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_cancelling_cooldown_close_does_not_cancel_pending_persistence(capacity_sessions, monkeypatch) -> None:
    store = CooldownStore(capacity_sessions)
    entered = asyncio.Event()
    release = asyncio.Event()
    original = store._persist_until

    async def blocked_write(provider, model, until):
        entered.set()
        await release.wait()
        await original(provider, model, until)

    monkeypatch.setattr(store, "_persist_until", blocked_write)
    store.persist("approved-provider", "*", 3600)
    await asyncio.wait_for(entered.wait(), timeout=1)
    closing = asyncio.create_task(store.aclose())
    try:
        await asyncio.sleep(0)
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert store.pending_count == 1
        release.set()
        await store.aclose()
        assert store.failed_writes == 0
        assert ("approved-provider", "*") in await store.load_active()
    finally:
        release.set()
        await asyncio.gather(closing, return_exceptions=True)
        await asyncio.gather(store.aclose(), return_exceptions=True)


async def test_atomic_cooldown_upserts_and_restart_preserve_the_longest_deadline(capacity_sessions) -> None:
    first, second = CooldownStore(capacity_sessions), CooldownStore(capacity_sessions)
    now = datetime.now(timezone.utc)
    longest = now + timedelta(seconds=3600)
    await asyncio.gather(
        first._persist_until("approved-provider", "*", longest),
        second._persist_until("approved-provider", "*", now + timedelta(seconds=60)),
    )
    await second._persist_until("approved-provider", "*", now + timedelta(seconds=120))
    async with capacity_sessions() as session:
        rows = (await session.execute(select(ModelRegistry))).scalars().all()
    assert len(rows) == 1
    assert rows[0].cooldown_until.replace(tzinfo=timezone.utc) == longest
    restored = await CooldownStore(capacity_sessions).load_active(clock=lambda: 100.0)
    assert 3695 < restored[("approved-provider", "*")] <= 3700


@pytest.mark.parametrize("owner", [None, "immutable-owner"])
async def test_provenance_replay_preserves_owner_and_does_not_promote_requested_alias(capacity_sessions, owner) -> None:
    async with capacity_sessions() as session:
        session.add(LLMRequests(
            request_id="historical-alias", owner_id=owner, task=TaskType.PERSONA_RESPONSE,
            request_model="requested-auto-alias", response_model=None,
            served_by_provider="approved-provider", success=True,
        ))
        await session.commit()

    [record] = await load_todays_provenance(capacity_sessions)
    assert record.owner_user_id == owner
    assert record.served_by_model == "unknown"
    assert record.data_classification == "unknown"
    assert record.processing_policy_id is None
    assert record.persistence_status == "acknowledged"


async def test_daily_replay_counts_failed_and_aborted_work_without_recounting_cache(capacity_sessions) -> None:
    async with capacity_sessions() as session:
        for request_id, outcome, consumption in [
            ("failed", "failed", "known"), ("aborted", "aborted", "unknown"), ("cached", "cached", "none"),
        ]:
            session.add(LLMRequests(
                request_id=request_id, task=TaskType.PERSONA_RESPONSE, success=False,
                attempts=[{
                    "attempt_number": 1, "provider": "openrouter", "model": "verified:free",
                    "observations": [{
                        "provider": "openrouter", "requested_model": "verified:free",
                        "outcome": outcome, "consumption": consumption,
                    }],
                }],
            ))
        await session.commit()
    requests, tokens = await load_todays_consumption(capacity_sessions)
    assert requests == {"openrouter": 2}
    assert tokens == {"openrouter": 0}


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
async def test_invalid_cooldown_duration_is_rejected_before_scheduling(capacity_sessions, duration) -> None:
    store = CooldownStore(capacity_sessions)
    try:
        with pytest.raises(ValueError, match="(?i)(finite|positive|duration)"):
            store.persist("approved-provider", "*", duration)
        assert store.pending_count == 0
    finally:
        await store.aclose()