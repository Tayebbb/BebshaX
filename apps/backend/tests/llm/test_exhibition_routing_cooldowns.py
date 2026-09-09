import pytest

from bebshax.llm import ChatMessage, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import AllCandidatesFailed, AttemptFailed, FailureKind
from bebshax.llm.types import LLMResult


RETRY_AFTER_S = 24 * 3600.0


class RetryAfterFakeAdapter(FakeAdapter):
    async def complete(
        self, candidate: RouteCandidate, request: LLMRequest
    ) -> AdapterCompletion:
        try:
            return await super().complete(candidate, request)
        except AttemptFailed as failure:
            raise AttemptFailed(
                failure.kind,
                candidate.provider,
                candidate.model,
                failure.detail,
                retry_after_s=RETRY_AFTER_S,
            ) from failure


async def _run(router: PoolRouter, *, streaming: bool) -> LLMResult:
    request = LLMRequest(
        task=TaskType.PERSONA_GENERATION,
        messages=[ChatMessage(role="user", content="Synthetic routing check")],
    )
    if streaming:
        events = [event async for event in router.stream(request)]
        assert isinstance(events[-1], LLMResult)
        return events[-1]
    return await router.complete(request)


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
@pytest.mark.parametrize(
    "failure_kind",
    [FailureKind.QUOTA_EXHAUSTED, FailureKind.AUTH_INVALID, FailureKind.RATE_LIMITED],
)
async def test_sole_provider_is_not_probed_before_retry_after_expires(
    failure_kind: FailureKind, streaming: bool
) -> None:
    now = [0.0]
    candidate = RouteCandidate(provider="openrouter", model="model-a")
    adapter = RetryAfterFakeAdapter([FakeRoute(candidate, behaviors=[failure_kind])])
    records = []
    router = PoolRouter(
        {"openrouter": adapter, "freellmpool": FakeAdapter([]), "ollama": FakeAdapter([])},
        clock=lambda: now[0],
        on_provenance=records.append,
    )

    with pytest.raises(AllCandidatesFailed):
        await _run(router, streaming=streaming)
    assert records[-1].attempts[0].failure_kind == failure_kind

    now[0] = RETRY_AFTER_S - 1.0
    with pytest.raises(AllCandidatesFailed):
        await _run(router, streaming=streaming)
    assert adapter.calls == ["openrouter/model-a"]
    assert records[-1].attempts == []
    assert any("provider-wide" in step for step in records[-1].routing_path)

    now[0] = RETRY_AFTER_S
    result = await _run(router, streaming=streaming)
    assert result.provider == candidate.provider
    assert result.provenance.success
    assert adapter.calls == ["openrouter/model-a", "openrouter/model-a"]


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
async def test_restored_provider_cooldown_is_not_bypassed_when_every_route_is_cooling(
    streaming: bool,
) -> None:
    remote = FakeAdapter([FakeRoute(RouteCandidate(provider="openrouter", model="model-a"))])
    local = FakeAdapter([FakeRoute(RouteCandidate(provider="ollama", model="local-model"))])
    router = PoolRouter(
        {"openrouter": remote, "freellmpool": FakeAdapter([]), "ollama": local},
        clock=lambda: 0.0,
        initial_cooldowns={
            ("openrouter", "*"): 100.0,
            ("openrouter", "model-a"): 80.0,
            ("ollama", "local-model"): 200.0,
        },
    )

    result = await _run(router, streaming=streaming)

    assert result.provider == "ollama"
    assert remote.calls == []
    assert local.calls == ["ollama/local-model"]


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
async def test_transient_route_cooldown_still_allows_a_half_open_probe(
    streaming: bool,
) -> None:
    candidate = RouteCandidate(provider="openrouter", model="model-a")
    adapter = FakeAdapter([FakeRoute(candidate)])
    router = PoolRouter(
        {"openrouter": adapter, "freellmpool": FakeAdapter([]), "ollama": FakeAdapter([])},
        clock=lambda: 0.0,
        initial_cooldowns={(candidate.provider, candidate.model): 60.0},
    )

    result = await _run(router, streaming=streaming)

    assert result.provider == candidate.provider
    assert adapter.calls == ["openrouter/model-a"]
    assert any("cooldown probe" in step for step in result.provenance.routing_path)


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
@pytest.mark.parametrize(
    "failure_kind",
    [FailureKind.QUOTA_EXHAUSTED, FailureKind.AUTH_INVALID, FailureKind.RATE_LIMITED],
)
async def test_probe_rechecks_new_provider_cooldown_before_trying_sibling_models(
    failure_kind: FailureKind, streaming: bool
) -> None:
    remote = RetryAfterFakeAdapter(
        [
            FakeRoute(
                RouteCandidate(provider="openrouter", model="model-a"),
                behaviors=[failure_kind],
            ),
            FakeRoute(RouteCandidate(provider="openrouter", model="model-b")),
        ]
    )
    local = FakeAdapter([FakeRoute(RouteCandidate(provider="ollama", model="local-model"))])
    router = PoolRouter(
        {"openrouter": remote, "freellmpool": FakeAdapter([]), "ollama": local},
        clock=lambda: 0.0,
        initial_cooldowns={
            ("openrouter", "model-a"): 60.0,
            ("openrouter", "model-b"): 90.0,
            ("ollama", "local-model"): 120.0,
        },
    )

    result = await _run(router, streaming=streaming)

    assert result.provider == "ollama"
    assert remote.calls == ["openrouter/model-a"]
    assert local.calls == ["ollama/local-model"]
    assert [attempt.failure_kind for attempt in result.provenance.attempts] == [
        failure_kind,
        None,
    ]
    assert any("provider-wide" in step for step in result.provenance.routing_path)