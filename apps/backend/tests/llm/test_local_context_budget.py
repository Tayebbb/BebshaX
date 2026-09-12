"""Remote context eligibility preserves the requested full report/output budget."""

from bebshax.llm import ChatMessage, LLMRequest, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.estimator import estimate_request_tokens


async def test_report_budget_selects_a_larger_remote_route_without_shrinking_output() -> None:
    request = LLMRequest(
        task=TaskType.REPORT_GENERATION,
        messages=[ChatMessage(role="user", content="complete source evidence " * 3000)],
        max_output_tokens=16000,
    )
    original = request.model_dump()
    adapter = FakeAdapter([
        FakeRoute(candidate=RouteCandidate(provider="remote", model="small", context_window=8192)),
        FakeRoute(candidate=RouteCandidate(provider="remote", model="large", context_window=131072)),
    ])
    result = await SingleAdapterLLMService(adapter).complete(request)
    assert result.model == "large"
    assert request.model_dump() == original
    assert result.provenance.estimated_tokens == estimate_request_tokens(request)
    assert adapter.calls == ["remote/large"]
