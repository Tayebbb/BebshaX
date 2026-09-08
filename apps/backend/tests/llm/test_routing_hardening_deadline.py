"""Routing hardening: per-kind cooldown durations and the whole-request budget.

A TIMEOUT cools its route briefly (30 s) so the next request in a batch does not
wait on the same stalled route; the fallback chain stops advancing once the
task's wall-clock budget is spent and reports the trail so far.
"""

import pytest

from bebshax.llm import AllCandidatesFailed, ChatMessage, FailureKind, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import FAILURE_POLICIES, AttemptFailed
from bebshax.llm.latency import REQUEST_DEADLINE_CAP_S, attempt_timeout_s, request_deadline_s
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.service import attempt_candidates
from bebshax.llm.types import TokenUsage


def _request(task: TaskType = TaskType.PERSONA_GENERATION) -> LLMRequest:
    return LLMRequest(task=task, messages=[ChatMessage(role="user", content="hello")])


def _route(provider: str, model: str, behaviors: list | None = None) -> FakeRoute:
    return FakeRoute(candidate=RouteCandidate(provider=provider, model=model), behaviors=behaviors or [])


def _router(remote_routes, local_routes, **kwargs):
    adapters = {
        "openrouter": FakeAdapter([]),
        "freellmpool": FakeAdapter(remote_routes),
        "ollama": FakeAdapter(local_routes),
    }
    return PoolRouter(adapters, **kwargs), adapters


def test_timeout_policy_cools_the_route_for_thirty_seconds() -> None:
    policy = FAILURE_POLICIES[FailureKind.TIMEOUT]
    assert policy.cooldown_route is True and policy.cooldown_seconds == 30.0
    # Other kinds keep the router default (None).
    assert FAILURE_POLICIES[FailureKind.SERVER_ERROR].cooldown_seconds is None


async def test_timed_out_route_is_skipped_for_30s_then_retried() -> None:
    now = {"t": 0.0}
    changes: list[tuple[str, str, float]] = []
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.TIMEOUT])],
        [_route("ollama", "m")],
        cooldown_seconds=60.0,
        clock=lambda: now["t"],
        on_cooldown_change=lambda p, m, s: changes.append((p, m, s)),
    )
    first = await router.complete(_request())
    assert first.provider == "ollama"
    assert changes == [("freellmpool", "auto", 30.0)]  # kind-specific duration persisted

    now["t"] = 29.0
    second = await router.complete(_request())
    assert second.provider == "ollama" and len(adapters["freellmpool"].calls) == 1
    assert any("cooling down for 1s" in step for step in second.provenance.routing_path)

    now["t"] = 31.0  # the short timeout cooldown has expired (the 60 s default has not)
    third = await router.complete(_request())
    assert third.provider == "freellmpool"


def test_request_deadline_is_a_bounded_multiple_of_the_attempt_budget() -> None:
    assert request_deadline_s(TaskType.PERSONA_INTERVIEW) == attempt_timeout_s(TaskType.PERSONA_INTERVIEW) * 2.5
    assert request_deadline_s(TaskType.REPORT_GENERATION) == REQUEST_DEADLINE_CAP_S  # 150 s * 2.5 capped


class _SlowFailingAdapter(FakeAdapter):
    """Every attempt 'takes' the clock forward and fails with SERVER_ERROR."""

    def __init__(self, routes, clock, step: float) -> None:
        super().__init__(routes)
        self._clock = clock
        self._step = step

    async def complete(self, candidate, request):
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        self._clock["t"] += self._step
        raise AttemptFailed(FailureKind.SERVER_ERROR, candidate.provider, candidate.model, "slow 5xx")


async def test_chain_stops_advancing_once_the_request_budget_is_spent(monkeypatch) -> None:
    import bebshax.llm.service as service_mod

    clock = {"t": 0.0}
    monkeypatch.setattr(service_mod.time, "perf_counter", lambda: clock["t"])
    routes = [_route("p", f"m{i}") for i in range(5)]
    adapter = _SlowFailingAdapter(routes, clock, step=40.0)
    provenance = ProvenanceRecord(request_id="r1", task="PERSONA_GENERATION", pool="reasoning")

    with pytest.raises(AllCandidatesFailed) as info:
        await attempt_candidates([(adapter, r.candidate) for r in routes], _request(), provenance, deadline_s=100.0)
    # 40 s, 80 s, 120 s -> the third failure crosses the 100 s budget; routes 4-5 are never tried.
    assert len(adapter.calls) == 3
    assert info.value.provenance.attempts[-1].fallback_reason == "stopping: request budget of 100s spent"
    assert any(step.startswith("[deadline: 100s request budget spent after 3 attempt(s)]") for step in provenance.routing_path)


async def test_success_within_budget_is_unaffected() -> None:
    ok = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="p", model="m"), reply="fine")])
    provenance = ProvenanceRecord(request_id="r2", task="PERSONA_GENERATION", pool="reasoning")
    result = await attempt_candidates([(ok, RouteCandidate(provider="p", model="m"))], _request(), provenance)
    assert isinstance(result.usage, TokenUsage) and result.text == "fine"
    assert isinstance(await ok.complete(RouteCandidate(provider="p", model="m"), _request()), AdapterCompletion)


# ---------------------------------------------------------------------------
# Cooldown probe (half-open breaker). Observed live: one 75 s freellmpool
# timeout benched the ONLY keyless route for 30 s and every feature failed in
# 0 ms with all_candidates_failed until it expired. A breaker that never lets a
# probe through learns nothing and blacks out the product.
# ---------------------------------------------------------------------------

async def test_sole_cooling_route_is_probed_instead_of_failing_in_zero_ms() -> None:
    now = {"t": 0.0}
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.TIMEOUT])],
        [],  # no local route: after the timeout NOTHING is eligible
        clock=lambda: now["t"],
    )
    with pytest.raises(AllCandidatesFailed):
        await router.complete(_request())  # times out, cools for 30 s
    assert len(adapters["freellmpool"].calls) == 1

    now["t"] = 5.0  # still cooling — a plain skip would fail with zero attempts
    second = await router.complete(_request())
    assert second.provider == "freellmpool" and len(adapters["freellmpool"].calls) == 2
    assert any("cooldown probe" in step for step in second.provenance.routing_path)
    assert second.provenance.attempts[-1].success is True


async def test_probe_prefers_the_route_that_recovers_soonest() -> None:
    now = {"t": 0.0}
    router, adapters = _router(
        [_route("freellmpool", "auto")],
        [_route("ollama", "m")],
        clock=lambda: now["t"],
        initial_cooldowns={("freellmpool", "auto"): 50.0, ("ollama", "m"): 20.0},
    )
    result = await router.complete(_request())
    assert result.provider == "ollama"  # 20 s left beats 50 s left, despite pool order
    assert adapters["freellmpool"].calls == []


async def test_failed_probe_rearms_the_cooldown_and_stays_honest() -> None:
    now = {"t": 0.0}
    changes: list[tuple[str, str, float]] = []
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.TIMEOUT, FailureKind.TIMEOUT])],
        [],
        clock=lambda: now["t"],
        on_cooldown_change=lambda p, m, s: changes.append((p, m, s)),
    )
    with pytest.raises(AllCandidatesFailed):
        await router.complete(_request())
    now["t"] = 10.0
    with pytest.raises(AllCandidatesFailed) as info:  # the probe fails too — reported, not hidden
        await router.complete(_request())
    assert len(adapters["freellmpool"].calls) == 2
    assert info.value.provenance.attempts[-1].failure_kind == FailureKind.TIMEOUT
    assert changes == [("freellmpool", "auto", 30.0), ("freellmpool", "auto", 30.0)]
    assert router.is_cooling(RouteCandidate(provider="freellmpool", model="auto"))


async def test_only_one_probe_per_route_is_in_flight() -> None:
    import asyncio

    gate = asyncio.Event()

    class SlowAdapter(FakeAdapter):
        async def complete(self, candidate, request):
            await gate.wait()
            return await super().complete(candidate, request)

    slow = SlowAdapter([_route("freellmpool", "auto")])
    router = PoolRouter(
        {"openrouter": FakeAdapter([]), "freellmpool": slow, "ollama": FakeAdapter([])},
        clock=lambda: 0.0,
        initial_cooldowns={("freellmpool", "auto"): 30.0},
    )
    first = asyncio.create_task(router.complete(_request()))
    for _ in range(200):
        if router.pool_utilization()["reasoning"]["active_requests"] == 1:
            break
        await asyncio.sleep(0.005)
    try:
        with pytest.raises(AllCandidatesFailed) as info:  # second caller waits its turn instead of stampeding
            await router.complete(_request())
        assert not info.value.provenance.attempts
        assert any("cooling down" in step for step in info.value.provenance.routing_path)
    finally:
        gate.set()
    assert (await first).provider == "freellmpool"


async def test_probe_never_admits_an_incapable_route() -> None:
    """Capability and context exclusions are not cooldowns — they stay excluded."""
    router, adapters = _router(
        [FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="tiny", context_window=8), reply="x")],
        [],
        clock=lambda: 0.0,
        initial_cooldowns={("freellmpool", "tiny"): 30.0},
    )
    with pytest.raises(Exception) as info:
        await router.complete(_request())
    assert adapters["freellmpool"].calls == []
    assert "ContextWindowExceeded" in type(info.value).__name__ or isinstance(info.value, AllCandidatesFailed)


# ---------------------------------------------------------------------------
# Provider recovery hints. Observed live: OpenRouter's free-tier DAY cap
# (resets at 00:00 UTC) was classified as a 60 s rate limit, so every minute a
# request burned an attempt on a route that could not serve until midnight.
# ---------------------------------------------------------------------------

class _HintingAdapter(FakeAdapter):
    def __init__(self, routes, kind: FailureKind, retry_after_s: float) -> None:
        super().__init__(routes)
        self._kind, self._hint = kind, retry_after_s

    async def complete(self, candidate, request):
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        raise AttemptFailed(self._kind, candidate.provider, candidate.model, "quota", retry_after_s=self._hint)


async def test_router_cools_a_route_for_the_providers_own_reset_hint() -> None:
    now = {"t": 0.0}
    changes: list[tuple[str, str, float]] = []
    quota = _HintingAdapter([_route("openrouter", "m")], FailureKind.QUOTA_EXHAUSTED, retry_after_s=3600.0)
    router = PoolRouter(
        {"openrouter": quota, "freellmpool": FakeAdapter([]), "ollama": FakeAdapter([_route("ollama", "local")])},
        clock=lambda: now["t"],
        on_cooldown_change=lambda p, m, s: changes.append((p, m, s)),
    )
    result = await router.complete(_request())
    assert result.provider == "ollama"
    assert changes == [("openrouter", "*", 3600.0)]  # provider-wide, for the hinted hour
    now["t"] = 3000.0
    assert router.is_cooling(RouteCandidate(provider="openrouter", model="m"))
    now["t"] = 3601.0
    assert not router.is_cooling(RouteCandidate(provider="openrouter", model="m"))


async def test_hint_is_bounded_and_never_shortens_the_policy_cooldown() -> None:
    changes: list[tuple[str, str, float]] = []
    long_hint = _HintingAdapter([_route("openrouter", "m")], FailureKind.QUOTA_EXHAUSTED, retry_after_s=10 * 86400.0)
    short_hint = _HintingAdapter([_route("freellmpool", "auto")], FailureKind.RATE_LIMITED, retry_after_s=5.0)
    router = PoolRouter(
        {"openrouter": long_hint, "freellmpool": short_hint, "ollama": FakeAdapter([_route("ollama", "local")])},
        cooldown_seconds=60.0,
        clock=lambda: 0.0,
        on_cooldown_change=lambda p, m, s: changes.append((p, m, s)),
    )
    await router.complete(_request())
    assert changes == [("openrouter", "*", 86400.0), ("freellmpool", "*", 60.0)]
