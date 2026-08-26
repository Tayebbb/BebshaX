import pytest

from bebshax.llm import (
    AllCandidatesFailed,
    ChatMessage,
    FailureKind,
    LLMRequest,
    PoolConfig,
    PoolRouter,
    TaskType,
)
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


def _request(task: TaskType = TaskType.PERSONA_GENERATION, **kwargs) -> LLMRequest:
    return LLMRequest(task=task, messages=[ChatMessage(role="user", content="hello")], **kwargs)


def _route(provider: str, model: str, behaviors: list | None = None, **cand) -> FakeRoute:
    return FakeRoute(
        candidate=RouteCandidate(provider=provider, model=model, **cand),
        behaviors=behaviors or [],
    )


def _router(remote_routes, local_routes, **kwargs):
    adapters = {
        "openrouter": FakeAdapter([]),  # registered but keyless → contributes no routes
        "freellmpool": FakeAdapter(remote_routes),
        "ollama": FakeAdapter(local_routes),
    }
    return PoolRouter(adapters, **kwargs), adapters


async def test_remote_pool_exhausted_falls_back_to_local() -> None:
    # Brief acceptance TEST 6: all remote fails → local serves.
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.PROVIDER_UNAVAILABLE])],
        [_route("ollama", "llama3.2:3b")],
    )
    result = await router.complete(_request())
    assert result.provider == "ollama"
    p = result.provenance
    assert p.pool == "reasoning"
    assert p.attempts[0].failure_kind == FailureKind.PROVIDER_UNAVAILABLE
    assert p.served_by_model == "llama3.2:3b"


async def test_tasks_resolve_to_their_configured_pools() -> None:
    router, _ = _router([_route("freellmpool", "auto")], [_route("ollama", "m")])
    interview = await router.complete(_request(task=TaskType.PERSONA_INTERVIEW))
    assert interview.provenance.pool == "conversation"
    structured = await router.complete(_request(task=TaskType.STRUCTURED_OUTPUT))
    assert structured.provenance.pool == "structured"


async def test_emergency_pool_prefers_local_and_skips_remote() -> None:
    router, adapters = _router([_route("freellmpool", "auto")], [_route("ollama", "m")])
    result = await router.complete(_request(task=TaskType.EMERGENCY_FALLBACK))
    assert result.provider == "ollama"
    assert result.provenance.pool == "emergency"
    assert adapters["freellmpool"].calls == []  # local-first: remote never touched


async def test_rate_limited_route_cools_down_then_recovers() -> None:
    now = {"t": 0.0}
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.RATE_LIMITED])],
        [_route("ollama", "m")],
        cooldown_seconds=60.0,
        clock=lambda: now["t"],
    )
    first = await router.complete(_request())
    assert first.provider == "ollama"
    assert len(adapters["freellmpool"].calls) == 1

    second = await router.complete(_request())  # inside cooldown window
    assert second.provider == "ollama"
    assert len(adapters["freellmpool"].calls) == 1  # remote never re-attempted
    assert any("cooling down" in step for step in second.provenance.routing_path)

    now["t"] = 61.0  # cooldown expired
    third = await router.complete(_request())
    assert third.provider == "freellmpool"
    assert len(adapters["freellmpool"].calls) == 2


async def test_whole_pool_failing_raises_with_pool_in_provenance() -> None:
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.SERVER_ERROR])],
        [_route("ollama", "m", [FailureKind.TIMEOUT])],
    )
    with pytest.raises(AllCandidatesFailed) as exc:
        await router.complete(_request())
    assert exc.value.provenance.pool == "reasoning"
    assert len(exc.value.provenance.attempts) == 2


async def test_provenance_hook_receives_pool_on_failure_too() -> None:
    captured: list = []
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.SERVER_ERROR])],
        [_route("ollama", "m", [FailureKind.TIMEOUT])],
        on_provenance=captured.append,
    )
    with pytest.raises(AllCandidatesFailed):
        await router.complete(_request())
    assert captured and captured[0].pool == "reasoning"
    assert captured[0].success is False

def test_unknown_adapter_in_pool_config_raises() -> None:
    """Pool configs referencing unregistered adapters are a wiring bug — fail loudly at construction."""
    with pytest.raises(ValueError, match="missing"):
        PoolRouter(
            {"only": FakeAdapter([])},
            pools={"p": PoolConfig(name="p", adapters=["missing"])},
            task_pool_map={},
        )


async def test_pool_utilization_tracks_in_flight_requests() -> None:
    """M2: active_requests must be measured, never hardcoded."""
    import asyncio

    gate = asyncio.Event()

    class BlockingAdapter(FakeAdapter):
        async def complete(self, candidate, request):
            await gate.wait()
            return await super().complete(candidate, request)

    blocking = BlockingAdapter([_route("freellmpool", "auto")])
    router = PoolRouter(
        {"openrouter": FakeAdapter([]), "freellmpool": blocking, "ollama": FakeAdapter([])}
    )

    assert all(p["active_requests"] == 0 for p in router.pool_utilization().values())

    task = asyncio.create_task(router.complete(_request()))
    try:
        for _ in range(200):  # poll until the request is inside the semaphore
            if router.pool_utilization()["reasoning"]["active_requests"] == 1:
                break
            await asyncio.sleep(0.005)
        assert router.pool_utilization()["reasoning"]["active_requests"] == 1
    finally:
        gate.set()  # never leak a blocked task, even on assertion failure
    await task
    assert router.pool_utilization()["reasoning"]["active_requests"] == 0


async def test_pool_utilization_drains_to_zero_on_failure() -> None:
    """M2: the in-flight counter must decrement on the exception path too."""
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.SERVER_ERROR])],
        [_route("ollama", "m", [FailureKind.TIMEOUT])],
    )
    with pytest.raises(AllCandidatesFailed):
        await router.complete(_request())
    assert router.pool_utilization()["reasoning"]["active_requests"] == 0


async def test_is_cooling_is_public_and_truthful() -> None:
    """M2: observability uses a public API, not the router's privates."""
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.RATE_LIMITED])],
        [_route("ollama", "m")],
    )
    await router.complete(_request())  # 429 → freellmpool cools, ollama serves
    cooling = _route("freellmpool", "auto").candidate
    warm = _route("ollama", "m").candidate
    assert router.is_cooling(cooling) is True
    assert router.is_cooling(warm) is False


async def test_preferred_model_is_prioritized_over_pool_order() -> None:
    """§7 model selection: an explicit preference wins over configured order."""
    router, _ = _router(
        [_route("freellmpool", "auto")],
        [_route("ollama", "llama3.2:3b")],
    )
    result = await router.complete(
        _request(preferred_provider="ollama", preferred_model="llama3.2:3b")
    )
    assert (result.provider, result.model) == ("ollama", "llama3.2:3b")
    assert any("preference ollama/llama3.2:3b" in step for step in result.provenance.routing_path)


async def test_unavailable_preference_degrades_to_auto() -> None:
    """§7: a preference is advisory — missing route falls back to Auto order."""
    router, _ = _router(
        [_route("freellmpool", "auto")],
        [_route("ollama", "m")],
    )
    result = await router.complete(_request(preferred_model="gpt-nonexistent"))
    assert (result.provider, result.model) == ("freellmpool", "auto")


async def test_no_preference_is_pure_auto() -> None:
    router, _ = _router([_route("freellmpool", "auto")], [_route("ollama", "m")])
    result = await router.complete(_request())
    assert result.provider == "freellmpool"
    assert not any("preference" in step for step in result.provenance.routing_path)
