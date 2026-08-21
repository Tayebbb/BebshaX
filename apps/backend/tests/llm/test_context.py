import pytest

from bebshax.llm import (
    ChatMessage,
    ContextWindowExceeded,
    LLMRequest,
    SingleAdapterLLMService,
    TaskType,
)
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


def _big_request(chars: int) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,
        messages=[ChatMessage(role="user", content="x" * chars)],
        max_output_tokens=100,
    )


def _route(model: str, window: int) -> FakeRoute:
    return FakeRoute(candidate=RouteCandidate(provider="fake", model=model, context_window=window))


async def test_small_context_models_are_skipped_not_called() -> None:
    adapter = FakeAdapter(
        [_route("small-32k", 32_000), _route("mid-64k", 64_000), _route("big-128k", 128_000)]
    )
    # ~100k input tokens: only the 128k model is eligible
    result = await SingleAdapterLLMService(adapter).complete(_big_request(400_000))
    assert result.model == "big-128k"
    assert adapter.calls == ["fake/big-128k"]  # smaller models never invoked
    assert any("skipped: context" in step for step in result.provenance.routing_path)


async def test_no_model_fits_raises_explicitly_and_never_truncates() -> None:
    adapter = FakeAdapter([_route("small-32k", 32_000)])
    with pytest.raises(ContextWindowExceeded) as exc:
        await SingleAdapterLLMService(adapter).complete(_big_request(400_000))
    assert exc.value.largest_window == 32_000
    assert exc.value.estimated_tokens > 32_000
    assert adapter.calls == []  # nothing was ever sent — no silent degradation
