"""Fast-routing memory: freellmpool routing="fast" latency metrics are
seeded from llm_requests at startup so the fast ranking survives restarts
instead of re-learning per process."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.db.capacity_state import load_recent_route_observations
from bebshax.db.models import Base, LLMRequests
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.types import TaskType


class _RecordingMetrics:
    def __init__(self) -> None:
        self.successes: list[tuple[str, float]] = []

    def record_success(self, key: str, latency_ms: float) -> None:
        self.successes.append((key, latency_ms))


class _MetricsPool:
    def __init__(self) -> None:
        self.metrics = _RecordingMetrics()

    async def aclose(self) -> None:
        pass


def _attempt(provider: str, model: str, latency_ms, success=True) -> dict:
    return {
        "attempt_number": 1,
        "provider": provider,
        "model": model,
        "latency_ms": latency_ms,
        "success": success,
    }


@pytest.fixture
async def seeded_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        session.add_all(
            [
                # oldest: concrete freellmpool target
                LLMRequests(
                    request_id="s1", task=TaskType.PERSONA_RESPONSE, success=True,
                    created_at=now - timedelta(hours=3),
                    attempts=[_attempt("llm7", "gpt-4o-mini", 1200.0)],
                ),
                # ollama-served — local adapter, never a freellmpool target
                LLMRequests(
                    request_id="s2", task=TaskType.PERSONA_RESPONSE, success=True,
                    created_at=now - timedelta(hours=2),
                    attempts=[_attempt("ollama", "llama3.2:3b", 900.0)],
                ),
                # failed freellmpool attempt (virtual name) then openrouter success
                LLMRequests(
                    request_id="s3", task=TaskType.PERSONA_GENERATION, success=True,
                    created_at=now - timedelta(hours=1),
                    attempts=[
                        _attempt("freellmpool", "auto", 5000.0, success=False),
                        _attempt("openrouter", "meta-llama/llama-3.3-70b-instruct:free", 2100.0),
                    ],
                ),
                # unsuccessful request — must not contribute
                LLMRequests(
                    request_id="s4", task=TaskType.PERSONA_RESPONSE, success=False,
                    created_at=now - timedelta(minutes=30),
                    attempts=[_attempt("llm7", "gpt-4o-mini", 800.0, success=False)],
                ),
                # too old — outside the window
                LLMRequests(
                    request_id="s5", task=TaskType.PERSONA_RESPONSE, success=True,
                    created_at=now - timedelta(days=10),
                    attempts=[_attempt("pollinations", "openai", 700.0)],
                ),
                # success but attempt has no latency — must be skipped
                LLMRequests(
                    request_id="s6", task=TaskType.PERSONA_RESPONSE, success=True,
                    created_at=now - timedelta(minutes=10),
                    attempts=[_attempt("kilo", "stepfun/step-3.7-flash:free", None)],
                ),
            ]
        )
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_loader_returns_concrete_targets_chronologically(seeded_db):
    obs = await load_recent_route_observations(seeded_db, days=3)
    # only concrete, successful, latency-bearing, in-window observations —
    # ollama and the virtual "freellmpool" name are excluded
    assert obs == [
        ("llm7", "gpt-4o-mini", 1200.0),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", 2100.0),
    ]


@pytest.mark.asyncio
async def test_loader_failure_degrades_to_cold_start(tmp_path):
    # a sessionmaker over a missing table must yield [] — never break startup
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    assert await load_recent_route_observations(maker) == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_loader_caps_observations_per_target(tmp_path):
    """Seeded ok-counts must never dilute live failure signal: only the
    NEWEST few observations per target are kept (critic finding)."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cap.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with maker() as session:
        session.add_all(
            [
                LLMRequests(
                    request_id=f"c{i}", task=TaskType.PERSONA_RESPONSE, success=True,
                    created_at=now - timedelta(minutes=60 - i),
                    attempts=[_attempt("llm7", "hot-model", 1000.0 + i)],
                )
                for i in range(12)
            ]
        )
        await session.commit()

    obs = await load_recent_route_observations(maker, per_target_cap=3)
    assert len(obs) == 3
    # the newest three, still chronological (oldest of the three first)
    assert [o[2] for o in obs] == [1009.0, 1010.0, 1011.0]
    await engine.dispose()


@pytest.mark.asyncio
async def test_adapter_seeds_pool_metrics_with_target_keys():
    pool = _MetricsPool()
    adapter = FreellmpoolAdapter(pool=pool, routing="fast")
    n = await adapter.seed_metrics(
        [
            ("llm7", "gpt-4o-mini", 1200.0),
            ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", 2100.0),
            ("llm7", "gpt-4o-mini", 950.0),  # newer measurement of the same target
        ]
    )
    assert n == 3
    # keys follow freellmpool's Target.name convention "provider/model",
    # replayed in order so EWMA weights the newest measurement most
    assert pool.metrics.successes == [
        ("llm7/gpt-4o-mini", 1200.0),
        ("openrouter/meta-llama/llama-3.3-70b-instruct:free", 2100.0),
        ("llm7/gpt-4o-mini", 950.0),
    ]


@pytest.mark.asyncio
async def test_seeded_metrics_influence_fast_scoring():
    """End-to-end over the REAL freellmpool Metrics: a seeded fast target must
    outrank an unmeasured one, and a seeded slow target must rank behind it."""
    from freellmpool.metrics import Metrics

    class _RealMetricsPool:
        def __init__(self) -> None:
            self.metrics = Metrics()

        async def aclose(self) -> None:
            pass

    pool = _RealMetricsPool()
    adapter = FreellmpoolAdapter(pool=pool, routing="fast")
    await adapter.seed_metrics(
        [
            ("llm7", "fast-model", 800.0),
            ("pollinations", "slow-model", 45_000.0),
        ]
    )
    fast = pool.metrics.score("llm7/fast-model")
    slow = pool.metrics.score("pollinations/slow-model")
    unknown = pool.metrics.score("never/seen")
    assert fast < slow  # measured-fast ranks ahead of measured-slow
    assert fast < unknown  # and ahead of the unmeasured neutral baseline
    # measured-healthy-but-45s ranks BEHIND never-measured — the neutral
    # baseline sits between healthy-fast and pathological targets
    assert unknown < slow