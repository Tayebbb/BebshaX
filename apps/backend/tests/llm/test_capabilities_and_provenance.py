from bebshax.llm import ChatMessage, LLMRequest, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


async def test_json_mode_skips_models_without_json_support() -> None:
    adapter = FakeAdapter(
        [
            FakeRoute(candidate=RouteCandidate(provider="fake", model="no-json", supports_json=False)),
            FakeRoute(candidate=RouteCandidate(provider="fake", model="with-json", supports_json=True)),
        ]
    )
    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="give me JSON")],
        json_mode=True,
    )
    result = await SingleAdapterLLMService(adapter).complete(request)
    assert result.model == "with-json"
    assert adapter.calls == ["fake/with-json"]


async def test_tools_required_skips_models_without_tool_support() -> None:
    adapter = FakeAdapter(
        [
            FakeRoute(candidate=RouteCandidate(provider="fake", model="no-tools", supports_tools=False)),
            FakeRoute(candidate=RouteCandidate(provider="fake", model="with-tools", supports_tools=True)),
        ]
    )
    request = LLMRequest(
        task=TaskType.TOOL_CALLING,
        messages=[ChatMessage(role="user", content="call a tool")],
        tools_required=True,
    )
    result = await SingleAdapterLLMService(adapter).complete(request)
    assert result.model == "with-tools"
    assert adapter.calls == ["fake/with-tools"]


async def test_provenance_is_complete_and_delivered_to_hook() -> None:
    captured: list = []
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"))])
    service = SingleAdapterLLMService(adapter, on_provenance=captured.append)
    request = LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[ChatMessage(role="user", content="hi")],
        persona_id="persona-1",
        conversation_id="conv-1",
    )
    result = await service.complete(request)

    assert captured and captured[0] is result.provenance
    p = captured[0]
    assert p.request_id == request.request_id
    assert p.task == "PERSONA_RESPONSE"
    assert p.persona_id == "persona-1" and p.conversation_id == "conv-1"
    assert p.served_by_provider == "fake" and p.served_by_model == "m1"
    assert p.total_latency_ms is not None and p.attempts[0].latency_ms is not None
    assert p.input_tokens is not None and p.output_tokens is not None
    assert p.success


async def test_provenance_hook_fires_on_failure_too() -> None:
    import pytest

    from bebshax.llm import AllCandidatesFailed, FailureKind

    captured: list = []
    adapter = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="m1"),
                behaviors=[FailureKind.RATE_LIMITED],
            )
        ]
    )
    service = SingleAdapterLLMService(adapter, on_provenance=captured.append)
    request = LLMRequest(
        task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hi")]
    )
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request)
    assert captured and captured[0].success is False
    assert captured[0].total_latency_ms is not None
