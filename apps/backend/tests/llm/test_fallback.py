import pytest

from bebshax.llm import (
    AllCandidatesFailed,
    AttemptFailed,
    ChatMessage,
    FailureKind,
    LLMRequest,
    SingleAdapterLLMService,
    TaskType,
)
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


def _request(**kwargs) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_GENERATION,
        messages=[ChatMessage(role="user", content="hello")],
        **kwargs,
    )


def _route(provider: str, model: str, behaviors: list | None = None, **cand) -> FakeRoute:
    return FakeRoute(
        candidate=RouteCandidate(provider=provider, model=model, **cand),
        behaviors=behaviors or [],
    )


async def test_falls_through_429_and_timeout_to_success() -> None:
    adapter = FakeAdapter(
        [
            _route("prov_a", "model_a", [FailureKind.RATE_LIMITED]),
            _route("prov_b", "model_b", [FailureKind.TIMEOUT]),
            _route("prov_c", "model_c"),
        ]
    )
    result = await SingleAdapterLLMService(adapter).complete(_request())
    assert result.model == "model_c"
    p = result.provenance
    assert p.success and p.served_by_model == "model_c"
    assert [a.failure_kind for a in p.attempts] == [
        FailureKind.RATE_LIMITED,
        FailureKind.TIMEOUT,
        None,
    ]
    assert p.attempts[-1].success


async def test_connection_failure_retries_same_route_once() -> None:
    adapter = FakeAdapter([_route("prov_a", "model_a", [FailureKind.CONNECTION])])
    result = await SingleAdapterLLMService(adapter).complete(_request())
    assert result.model == "model_a"
    assert adapter.calls == ["prov_a/model_a", "prov_a/model_a"]
    assert len(result.provenance.attempts) == 2


async def test_all_candidates_failing_raises_with_full_provenance() -> None:
    adapter = FakeAdapter(
        [
            _route("prov_a", "model_a", [FailureKind.RATE_LIMITED]),
            _route("prov_b", "model_b", [FailureKind.SERVER_ERROR]),
        ]
    )
    with pytest.raises(AllCandidatesFailed) as exc:
        await SingleAdapterLLMService(adapter).complete(_request())
    attempts = exc.value.provenance.attempts
    assert len(attempts) == 2
    assert attempts[0].failure_kind == FailureKind.RATE_LIMITED
    assert attempts[1].failure_kind == FailureKind.SERVER_ERROR


async def test_internal_error_surfaces_instead_of_burning_candidates() -> None:
    adapter = FakeAdapter(
        [
            _route("prov_a", "model_a", [FailureKind.INTERNAL_ERROR]),
            _route("prov_b", "model_b"),
        ]
    )
    with pytest.raises(AttemptFailed):
        await SingleAdapterLLMService(adapter).complete(_request())
    assert adapter.calls == ["prov_a/model_a"]
