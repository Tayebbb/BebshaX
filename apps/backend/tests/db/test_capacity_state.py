"""AI plan §10: quota ledger math, quota-aware ranking, cooldown persistence."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

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
    assert ledger.remaining_fraction("ollama") == 1.0  # uncapped
    assert ledger.remaining_fraction("llm7") == 1.0  # unknown → default uncapped


def test_ranker_demotes_capped_provider_and_keeps_pool_order_otherwise() -> None:
    ledger = QuotaLedger()
    entries = [
        (None, RouteCandidate(provider="openrouter", model="a")),
        (None, RouteCandidate(provider="freellmpool", model="auto")),
        (None, RouteCandidate(provider="ollama", model="m")),
    ]
    rank = quota_aware_ranker(ledger)
    # Untouched quotas: stable sort preserves configured pool order.
    assert [c.provider for _, c in rank(entries)] == ["openrouter", "freellmpool", "ollama"]
    # Exhaust openrouter → it sinks below the others.
    for _ in range(PROVIDER_QUOTAS["openrouter"].rpd):
        ledger.record(_prov("openrouter", tokens=1))
    assert [c.provider for _, c in rank(entries)] == ["freellmpool", "ollama", "openrouter"]


@pytest.mark.asyncio
async def test_cooldown_store_round_trip(async_engine) -> None:
    maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    store = CooldownStore(maker)
    await store._persist_async("openrouter", "deepseek/deepseek-r1:free", 120.0)
    loaded = await store.load_active()
    assert ("openrouter", "deepseek/deepseek-r1:free") in loaded

    # Expired cooldowns are not restored
    await store._persist_async("groq", "llama-3.3-70b", -5.0)
    loaded = await store.load_active()
    assert ("groq", "llama-3.3-70b") not in loaded


@pytest.mark.asyncio
async def test_persist_upserts_single_registry_row(async_engine) -> None:
    from sqlalchemy import func, select

    maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    store = CooldownStore(maker)
    await store._persist_async("openrouter", "m", 60.0)
    await store._persist_async("openrouter", "m", 90.0)
    async with maker() as session:
        count = (
            await session.execute(select(func.count()).select_from(ModelRegistry))
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_ledger_seed_from_llm_requests(async_engine) -> None:
    from bebshax.db.sink import ProvenanceSink

    maker = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
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
            "openrouter": FakeAdapter([]),
            "freellmpool": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="auto"), behaviors=[FailureKind.RATE_LIMITED])]
            ),
            "ollama": FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="ollama", model="m"))]),
        },
        on_cooldown_change=lambda p, m, s: persisted.append((p, m, s)),
    )
    await router.complete(
        LLMRequest(task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")])
    )
    assert persisted == [("freellmpool", "auto", 60.0)]


@pytest.mark.asyncio
async def test_router_honours_initial_cooldowns() -> None:
    import time

    from bebshax.llm import ChatMessage, LLMRequest
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    router = PoolRouter(
        {
            "openrouter": FakeAdapter([]),
            "freellmpool": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="auto"), reply="remote")]
            ),
            "ollama": FakeAdapter(
                [FakeRoute(candidate=RouteCandidate(provider="ollama", model="m"), reply="local")]
            ),
        },
        initial_cooldowns={("freellmpool", "auto"): time.monotonic() + 300},
    )
    result = await router.complete(
        LLMRequest(task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")])
    )
    assert result.provider == "ollama"  # restored cooldown skipped the remote route
