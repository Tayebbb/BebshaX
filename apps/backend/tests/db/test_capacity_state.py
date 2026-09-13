"""AI plan §10: quota ledger math, quota-aware ranking, cooldown persistence."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bebshax.db.capacity_state import CooldownStore, load_todays_consumption
from bebshax.db.models import ModelRegistry
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.quota import PROVIDER_QUOTAS, QuotaLedger, quota_aware_ranker
from bebshax.llm.types import TaskType


def _prov(provider: str, tokens: int = 100, success: bool = True) -> ProvenanceRecord:
    import uuid

    return ProvenanceRecord(
        request_id=uuid.uuid4().hex,
        task=TaskType.PERSONA_GENERATION,
        served_by_provider=provider if success else None,
        input_tokens=tokens // 2,
        output_tokens=tokens - tokens // 2,
        success=success,
    )


def test_ledger_counts_only_successful_concrete_providers() -> None:
    ledger = QuotaLedger()
    ledger.record(_prov("openrouter"))
    ledger.record(_prov("openrouter"))
    ledger.record(_prov("groq", tokens=50))
    ledger.record(_prov("openrouter", success=False))  # no provider on failure
    assert ledger.used_today("openrouter") == (2, 200)
    assert ledger.used_today("groq") == (1, 50)


def test_remaining_fraction_hits_zero_at_published_cap() -> None:
    ledger = QuotaLedger()
    cap = PROVIDER_QUOTAS["openrouter"].rpd
    for _ in range(cap):
        ledger.record(_prov("openrouter", tokens=10))
    assert ledger.remaining_fraction("openrouter") == 0.0
    assert ledger.remaining_fraction("pollinations") == 1.0
    assert ledger.remaining_fraction("llm7") == 1.0  # unknown → default uncapped


def test_ranker_excludes_exhausted_provider_and_keeps_order_otherwise() -> None:
    ledger = QuotaLedger()
    entries = [
        (None, RouteCandidate(provider="openrouter", model="a")),
        (None, RouteCandidate(provider="freellmpool", model="auto")),
        (None, RouteCandidate(provider="llm7", model="m")),
    ]
    rank = quota_aware_ranker(ledger)
    # Untouched quotas: configured pool order is preserved.
    assert [c.provider for _, c in rank(entries)] == ["openrouter", "freellmpool", "llm7"]
    for _ in range(PROVIDER_QUOTAS["openrouter"].rpd):
        ledger.record(_prov("openrouter", tokens=1))
    assert [c.provider for _, c in rank(entries)] == ["freellmpool", "llm7"]


@pytest.mark.asyncio
async def test_cooldown_store_round_trip(async_engine) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    store = CooldownStore(maker)
    await store._persist_async("openrouter", "deepseek/deepseek-r1:free", 120.0)
    loaded = await store.load_active()
    assert ("openrouter", "deepseek/deepseek-r1:free") in loaded

    # Expired cooldowns are not restored
    async with maker() as session:
        session.add(ModelRegistry(
            id="expired-route", provider_name="groq", model_name="llama-3.3-70b",
            cooldown_until=datetime.now(timezone.utc) - timedelta(seconds=5),
        ))
        await session.commit()
    loaded = await store.load_active()
    assert ("groq", "llama-3.3-70b") not in loaded


@pytest.mark.parametrize("seconds", [0, -5, float("inf"), float("-inf"), float("nan")])
async def test_invalid_cooldown_duration_cannot_schedule_or_write(seconds: float) -> None:
    from unittest.mock import MagicMock

    maker = MagicMock()
    store = CooldownStore(maker)

    with pytest.raises(ValueError, match="finite and positive"):
        store.persist("groq", "*", seconds)
    with pytest.raises(ValueError, match="finite and positive"):
        await store._persist_async("groq", "*", seconds)

    assert store.pending_count == 0
    maker.assert_not_called()


@pytest.mark.asyncio
async def test_persist_upserts_single_registry_row(async_engine) -> None:
    from sqlalchemy import func, select

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    store = CooldownStore(maker)
    await store._persist_async("openrouter", "m", 60.0)
    await store._persist_async("openrouter", "m", 90.0)
    async with maker() as session:
        count = (
            await session.execute(select(func.count()).select_from(ModelRegistry))
        ).scalar_one()
    assert count == 1


async def test_shorter_cooldown_cannot_overwrite_longer_deadline(async_engine):
    from sqlalchemy import select

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    first_store, second_store = CooldownStore(maker), CooldownStore(maker)
    await first_store._persist_async("groq", "*", 300)
    async with maker() as session:
        original = (await session.execute(select(ModelRegistry.cooldown_until))).scalar_one()
    second_store.persist("groq", "*", 10)
    await second_store.drain()
    async with maker() as session:
        current = (await session.execute(select(ModelRegistry.cooldown_until))).scalar_one()
    assert current == original
    assert second_store.pending_count == 0


@pytest.mark.asyncio
async def test_ledger_seed_from_llm_requests(async_engine) -> None:
    from bebshax.db.sink import ProvenanceSink

    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    sink = ProvenanceSink(maker)
    await sink._insert_batch([_prov("openrouter", tokens=40), _prov("openrouter", tokens=60)])
    requests, tokens = await load_todays_consumption(maker)
    assert requests == {"openrouter": 2}
    assert tokens == {"openrouter": 100}
    ledger = QuotaLedger()
    ledger.seed(requests, tokens)
    assert ledger.used_today("openrouter") == (2, 100)


@pytest.mark.asyncio
async def test_router_persists_cooldowns_via_callback() -> None:
    from bebshax.llm import ChatMessage, FailureKind, LLMRequest
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    persisted: list[tuple[str, str, float]] = []
    router = PoolRouter(
        {
            "openrouter": FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="openrouter", model="secondary"))]),
            "freellmpool": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="auto"), behaviors=[FailureKind.RATE_LIMITED])]
            ),
        },
        on_cooldown_change=lambda p, m, s: persisted.append((p, m, s)),
    )
    await router.complete(
        LLMRequest(task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")])
    )
    # RATE_LIMITED is an account-level signal: its policy cools the whole
    # provider, persisted with the provider-wide model marker "*". The seconds
    # value is (now + 60) - now on a monotonic clock, so compare with tolerance.
    assert [(p, m) for p, m, _ in persisted] == [("freellmpool", "*")]
    assert persisted[0][2] == pytest.approx(60.0, abs=1e-6)


@pytest.mark.asyncio
async def test_provider_wide_cooldown_round_trips_through_store(async_engine) -> None:
    """The (provider, "*") key persists and loads back unchanged, so a
    provider-wide cooldown survives a restart with the same semantics."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    store = CooldownStore(maker)
    await store._persist_async("openrouter", "*", 120.0)
    loaded = await store.load_active()
    assert ("openrouter", "*") in loaded


@pytest.mark.asyncio
async def test_router_honours_initial_cooldowns() -> None:
    import time

    from bebshax.llm import ChatMessage, LLMRequest
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    router = PoolRouter(
        {
            "openrouter": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="openrouter", model="secondary"), reply="secondary")]
            ),
            "freellmpool": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="auto"), reply="remote")]
            ),
        },
        initial_cooldowns={("freellmpool", "auto"): time.monotonic() + 300},
    )
    result = await router.complete(
        LLMRequest(task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")])
    )
    assert result.provider == "openrouter"
