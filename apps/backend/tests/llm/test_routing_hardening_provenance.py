"""Provenance completeness: the pre-flight estimate, the request parameters
and any ranker re-ordering are visible in every ProvenanceRecord.

Regression: a route skipped as "context 8192 < ~9000" could not be audited
because the record never said what the estimate was based on, which sampling
parameters were sent, or why the attempt order differed from the pool order.
"""

from bebshax.llm import (
    ChatMessage,
    ContextWindowExceeded,
    LLMRequest,
    PoolRouter,
    SingleAdapterLLMService,
    TaskType,
)
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.estimator import DEFAULT_EXPECTED_OUTPUT_TOKENS, estimate_request_tokens


def _route(provider: str, model: str, **cand) -> FakeRoute:
    return FakeRoute(candidate=RouteCandidate(provider=provider, model=model, **cand))


def _marker(path: list[str], prefix: str) -> list[str]:
    return [s for s in path if s.startswith(prefix)]


async def test_provenance_carries_estimate_and_params_markers() -> None:
    adapter = FakeAdapter([_route("fake", "m1")])
    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="hello " * 50)],
        max_output_tokens=300,
        temperature=0.2,
        json_mode=True,
    )
    result = await SingleAdapterLLMService(adapter).complete(request)
    p = result.provenance

    estimate = estimate_request_tokens(request)
    assert p.estimated_tokens == estimate
    assert _marker(p.routing_path, "[context estimate") == [
        f"[context estimate ~{estimate} tokens incl. max_output 300]"
    ]
    assert _marker(p.routing_path, "[params") == [
        "[params temperature=0.2 max_output_tokens=300 json_mode=True]"
    ]
    # markers precede the route entries, and the route entry is still there
    assert p.routing_path.index("[params temperature=0.2 max_output_tokens=300 json_mode=True]") < (
        p.routing_path.index("fake/m1")
    )
    # the record round-trips through JSON with the new field (DB sink uses model_dump)
    assert p.model_dump(mode="json")["estimated_tokens"] == estimate


async def test_default_output_allowance_is_labelled_in_the_estimate_marker() -> None:
    adapter = FakeAdapter([_route("fake", "m1")])
    request = LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hi")])
    result = await SingleAdapterLLMService(adapter).complete(request)
    [marker] = _marker(result.provenance.routing_path, "[context estimate")
    assert marker.endswith(f"incl. max_output {DEFAULT_EXPECTED_OUTPUT_TOKENS} (default)]")
    [params] = _marker(result.provenance.routing_path, "[params")
    assert params == "[params temperature=None max_output_tokens=None json_mode=False]"


async def test_estimate_is_stamped_even_when_preflight_rejects_everything() -> None:
    import pytest

    records: list = []
    adapter = FakeAdapter([_route("fake", "tiny", context_window=1_000)])
    request = LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,
        messages=[ChatMessage(role="user", content="x" * 20_000)],
        max_output_tokens=100,
    )
    with pytest.raises(ContextWindowExceeded) as exc:
        await SingleAdapterLLMService(adapter, on_provenance=records.append).complete(request)
    assert records[0].estimated_tokens == exc.value.estimated_tokens
    assert _marker(records[0].routing_path, "[context estimate")


async def test_ranker_reordering_is_recorded_compactly() -> None:
    adapters = {
        "openrouter": FakeAdapter([_route("openrouter", "a")]),
        "freellmpool": FakeAdapter([_route("freellmpool", "auto")]),
        "ollama": FakeAdapter([_route("ollama", "m")]),
    }

    def demote_openrouter(entries):
        return [e for e in entries if e[1].provider != "openrouter"] + [
            e for e in entries if e[1].provider == "openrouter"
        ]

    router = PoolRouter(adapters, ranker=demote_openrouter)
    request = LLMRequest(
        task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")]
    )
    result = await router.complete(request)
    assert result.provider == "freellmpool"
    assert _marker(result.provenance.routing_path, "[ranker reordered") == [
        "[ranker reordered: openrouter/a, freellmpool/auto, ollama/m -> "
        "freellmpool/auto, ollama/m, openrouter/a]"
    ]


async def test_identity_ranker_leaves_no_reorder_marker() -> None:
    adapters = {
        "openrouter": FakeAdapter([_route("openrouter", "a")]),
        "freellmpool": FakeAdapter([_route("freellmpool", "auto")]),
        "ollama": FakeAdapter([_route("ollama", "m")]),
    }
    router = PoolRouter(adapters, ranker=lambda entries: list(entries))
    request = LLMRequest(
        task=TaskType.PERSONA_GENERATION, messages=[ChatMessage(role="user", content="hi")]
    )
    result = await router.complete(request)
    assert not _marker(result.provenance.routing_path, "[ranker reordered")
    # exactly one estimate marker per request — never duplicated by the pool path
    assert len(_marker(result.provenance.routing_path, "[context estimate")) == 1
