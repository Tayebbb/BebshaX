"""Exhaustion semantics: all-context-overflow ⇒ ContextWindowExceeded, and
adapter bugs ⇒ INTERNAL_ERROR that surfaces instead of burning candidates.

Regressions: (1) the freellmpool adapter advertises a virtual 1,000,000-token
window, so a prompt too large for EVERY real model passed pre-flight, every
attempt failed CONTEXT_WINDOW_EXCEEDED and the caller saw a generic
AllCandidatesFailed (503 "no route") instead of ContextWindowExceeded (413,
never truncate). (2) A non-AttemptFailed exception escaping an adapter was
never stamped on the attempt record (R6) and the persona generator templated
over it as if a provider had merely been flaky.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from bebshax.llm import (
    AllCandidatesFailed,
    AttemptFailed,
    ChatMessage,
    ContextWindowExceeded,
    FailureKind,
    LLMRequest,
    LLMResult,
    PoolRouter,
    SingleAdapterLLMService,
    TaskType,
)
from bebshax.llm.adapters.base import RouteCandidate, StreamDelta
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.pools import PoolConfig


def _request(task: TaskType = TaskType.PERSONA_GENERATION) -> LLMRequest:
    return LLMRequest(task=task, messages=[ChatMessage(role="user", content="hello")])


def _route(provider: str, model: str, behaviors: list | None = None, **cand) -> FakeRoute:
    return FakeRoute(
        candidate=RouteCandidate(provider=provider, model=model, **cand), behaviors=behaviors or []
    )


def _router(remote_routes, local_routes, **kwargs) -> tuple[PoolRouter, dict]:
    secondary = FakeAdapter(local_routes)
    adapters = {
        "openrouter": secondary,
        "freellmpool": FakeAdapter(remote_routes),
        "ollama": secondary,
    }
    return PoolRouter(adapters, **kwargs), adapters


# ---------------------------------------------------------------------------
# Task 5 — every attempt overflowed context ⇒ ContextWindowExceeded
# ---------------------------------------------------------------------------

async def test_all_routes_overflowing_context_raise_context_window_exceeded() -> None:
    records: list = []
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.CONTEXT_WINDOW_EXCEEDED])],
        [_route("ollama", "m", [FailureKind.CONTEXT_WINDOW_EXCEEDED])],
        on_provenance=records.append,
    )
    request = _request()
    with pytest.raises(ContextWindowExceeded) as exc:
        await router.complete(request)
    assert exc.value.estimated_tokens == estimate_request_tokens(request)
    assert exc.value.largest_window is None
    # both routes were really tried, and provenance still fired with the trail
    assert adapters["freellmpool"].calls == ["freellmpool/auto"]
    assert adapters["ollama"].calls == ["ollama/m"]
    assert records and records[0].success is False
    assert [a.failure_kind for a in records[0].attempts] == [
        FailureKind.CONTEXT_WINDOW_EXCEEDED,
        FailureKind.CONTEXT_WINDOW_EXCEEDED,
    ]
    assert records[0].estimated_tokens == exc.value.estimated_tokens


async def test_mixed_failures_still_raise_all_candidates_failed() -> None:
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.CONTEXT_WINDOW_EXCEEDED])],
        [_route("ollama", "m", [FailureKind.TIMEOUT])],
    )
    with pytest.raises(AllCandidatesFailed):
        await router.complete(_request())


async def test_single_adapter_service_has_the_same_exhaustion_semantics() -> None:
    adapter = FakeAdapter(
        [
            _route("p", "a", [FailureKind.CONTEXT_WINDOW_EXCEEDED]),
            _route("p", "b", [FailureKind.CONTEXT_WINDOW_EXCEEDED]),
        ]
    )
    with pytest.raises(ContextWindowExceeded):
        await SingleAdapterLLMService(adapter).complete(_request())


async def test_stream_loop_raises_context_window_exceeded_when_all_overflow() -> None:
    router, _ = _router(
        [_route("freellmpool", "auto", [FailureKind.CONTEXT_WINDOW_EXCEEDED])],
        [_route("ollama", "m", [FailureKind.CONTEXT_WINDOW_EXCEEDED])],
    )
    with pytest.raises(ContextWindowExceeded):
        async for _ in router.stream(_request(TaskType.PERSONA_INTERVIEW)):
            pass


# ---------------------------------------------------------------------------
# Task 6 — adapter bugs surface as INTERNAL_ERROR without advancing
# ---------------------------------------------------------------------------

class BuggyAdapter(FakeAdapter):
    """Raises a plain KeyError from complete()/stream() — our defect, not the provider's."""

    async def complete(self, candidate, request):
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        raise KeyError("prompt_tokens")

    async def stream(self, candidate, request):
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        raise KeyError("prompt_tokens")
        yield StreamDelta(text="unreachable")  # keeps this an async generator


async def test_adapter_bug_is_stamped_internal_error_and_next_candidate_never_called() -> None:
    records: list = []
    buggy = BuggyAdapter([_route("freellmpool", "auto")])
    healthy = FakeAdapter([_route("ollama", "m")])
    router = PoolRouter(
        {"openrouter": healthy, "freellmpool": buggy, "ollama": healthy},
        on_provenance=records.append,
    )
    with pytest.raises(AttemptFailed) as exc:
        await router.complete(_request())

    assert exc.value.kind == FailureKind.INTERNAL_ERROR
    assert (exc.value.provider, exc.value.model) == ("freellmpool", "auto")
    assert isinstance(exc.value.__cause__, KeyError)  # chained from the original
    assert healthy.calls == []  # never advanced past our own bug (R6)

    [attempt] = records[0].attempts
    assert attempt.failure_kind == FailureKind.INTERNAL_ERROR
    assert attempt.failure_detail is not None
    assert attempt.failure_detail.startswith("KeyError: ")
    assert attempt.latency_ms is not None
    assert attempt.fallback_reason is None
    assert records[0].success is False
    assert router.pool_utilization()["reasoning"]["active_requests"] == 0


async def test_internal_error_detail_is_bounded_to_300_chars() -> None:
    class VerboseBug(FakeAdapter):
        async def complete(self, candidate, request):
            raise ValueError("x" * 1000)

    records: list = []
    service = SingleAdapterLLMService(VerboseBug([_route("p", "m")]), on_provenance=records.append)
    with pytest.raises(AttemptFailed):
        await service.complete(_request())
    assert len(records[0].attempts[0].failure_detail) == 300


async def test_stream_loop_surfaces_adapter_bug_as_internal_error() -> None:
    records: list = []
    buggy = BuggyAdapter([_route("fake", "dead")])
    healthy = FakeAdapter([_route("fake2", "ok")])
    router = PoolRouter(
        {"a": buggy, "b": healthy},
        pools={"conversation": PoolConfig(name="conversation", adapters=["a", "b"])},
        task_pool_map={TaskType.PERSONA_INTERVIEW: "conversation"},
        on_provenance=records.append,
    )
    with pytest.raises(AttemptFailed) as exc:
        async for _ in router.stream(_request(TaskType.PERSONA_INTERVIEW)):
            pass
    assert exc.value.kind == FailureKind.INTERNAL_ERROR
    assert healthy.calls == []
    assert records[0].attempts[-1].failure_kind == FailureKind.INTERNAL_ERROR
    assert records[0].attempts[-1].failure_detail.startswith("KeyError: ")


async def test_scripted_failures_still_advance_normally() -> None:
    """Guard: the INTERNAL_ERROR catch-all must not swallow classified failures."""
    router, adapters = _router(
        [_route("freellmpool", "auto", [FailureKind.SERVER_ERROR])], [_route("ollama", "m")]
    )
    result = await router.complete(_request())
    assert isinstance(result, LLMResult) and result.provider == "ollama"
    assert adapters["ollama"].calls == ["ollama/m"]


# ---------------------------------------------------------------------------
# Task 6 — persona generator re-raises every LLMError instead of templating
# ---------------------------------------------------------------------------

class _Segment:
    def __init__(self, id: str, name: str) -> None:
        self.id = id
        self.name = name
        self.population_percentage = 100.0
        self.characteristics = {
            "demographics": {"age_range": [18, 24], "dominant_occupation": "Student"},
            "economics": {"monthly_budget": {"min": 250, "max": 600, "median": 425}},
            "behavior": {"study_hours_per_day": 4.0, "technology_familiarity": "High"},
            "needs": ["Affordable micro-billing"],
        }


def _study():
    study = MagicMock()
    study.title = "Exam Prep Platform"
    study.prompt = "Affordable study planning"
    study.target_audience = "College students"
    study.pricing_hypothesis = "৳300/month"
    return study


class _RaisingLLM:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete(self, request):
        raise self._exc


@pytest.mark.parametrize(
    "error",
    [
        AttemptFailed(FailureKind.INTERNAL_ERROR, "freellmpool", "auto", "KeyError: prompt_tokens"),
        ContextWindowExceeded(50_000, None),
    ],
    ids=["internal_error", "context_window_exceeded"],
)
async def test_generator_surfaces_llm_errors_instead_of_templating(error) -> None:
    from bebshax.personas.generator import generate_personas_for_study

    with pytest.raises(type(error)):
        await generate_personas_for_study(
            study=_study(),
            segments=[_Segment("seg_1", "Budget Students")],
            target_count=2,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=_RaisingLLM(error),
        )


async def test_generator_fails_explicitly_on_a_successful_but_unparseable_reply() -> None:
    """A reply that WAS produced but cannot be used is retried once, then the run
    fails with an explicit UnusableModelOutput — the former template path is gone."""
    from bebshax.personas.generator import generate_personas_for_study
    from bebshax.utils.explicit_failures import UnusableModelOutput

    class _GarbageLLM:
        async def complete(self, request):
            return SimpleNamespace(
                text="not json",
                provenance=SimpleNamespace(served_by_provider="fake", served_by_model="m"),
            )

    with pytest.raises(UnusableModelOutput) as exc_info:
        await generate_personas_for_study(
            study=_study(),
            segments=[_Segment("seg_1", "Budget Students")],
            target_count=2,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=_GarbageLLM(),
        )
    assert exc_info.value.error_code == "persona_generation_unparseable"
