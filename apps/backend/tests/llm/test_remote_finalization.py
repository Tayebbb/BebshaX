import asyncio

import pytest
from pydantic import ValidationError

from bebshax.llm import AllCandidatesFailed, ChatMessage, LLMRequest, LLMResult, PoolRouter, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate, StreamDelta, StreamDone
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.latency import ATTEMPT_TIMEOUTS_S
from bebshax.llm.pools import PoolConfig


def request(**changes):
    return LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="full input")], **changes)


def fake(reply="complete answer", **candidate_changes):
    return FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="remote", model="model", **candidate_changes), reply=reply)])


def router(adapter, callback):
    return PoolRouter(
        {"remote": adapter}, pools={"test": PoolConfig(name="test", adapters=["remote"])},
        task_pool_map={TaskType.PERSONA_RESPONSE: "test"}, on_provenance=callback,
    )


async def test_service_validates_json_even_if_an_adapter_claims_success():
    service = SingleAdapterLLMService(fake("prose only"))
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request(json_mode=True))


@pytest.mark.parametrize("text", ['[{"ok":true}', '{"ok":true}{"unfinished":', '{"ok":true} ['])
async def test_structured_validation_does_not_mine_a_complete_fragment_from_partial_output(text):
    with pytest.raises(AllCandidatesFailed):
        await SingleAdapterLLMService(fake(text)).complete(request(json_mode=True))


async def test_complete_prose_wrapped_json_object_remains_supported():
    result = await SingleAdapterLLMService(fake('Result:\n{"ok":true}\nComplete.')).complete(request(json_mode=True))
    assert result.text == 'Result:\n{"ok":true}\nComplete.'


async def test_tools_required_without_schemas_is_unavailable_even_when_advertised():
    adapter = fake(supports_tools=True)
    with pytest.raises(AllCandidatesFailed):
        await SingleAdapterLLMService(adapter).complete(request(tools_required=True))
    assert adapter.calls == []


@pytest.mark.parametrize("changes", [{"max_output_tokens": 0}, {"max_output_tokens": -1}, {"temperature": float("nan")}, {"temperature": -0.1}])
def test_invalid_generation_parameters_fail_before_dispatch(changes):
    with pytest.raises(ValidationError):
        request(**changes)


@pytest.mark.parametrize("single", [False, True])
async def test_async_provenance_callback_is_acknowledged_before_complete_returns(single):
    events = []

    async def persist(record):
        await asyncio.sleep(0)
        events.append(record.request_id)

    service = SingleAdapterLLMService(fake(), on_provenance=persist) if single else router(fake(), persist)
    result = await service.complete(request())
    assert events == [result.provenance.request_id]
    assert result.provenance.persistence_status == "acknowledged"


async def test_stream_terminal_is_not_emitted_before_async_provenance_acknowledgement():
    persisted = []

    async def persist(record):
        await asyncio.sleep(0)
        persisted.append(record.request_id)

    stream = router(fake(), persist).stream(request())
    try:
        assert isinstance(await anext(stream), StreamDelta)
        result = await anext(stream)
        assert isinstance(result, LLMResult)
        assert persisted == [result.provenance.request_id]
    finally:
        await stream.aclose()
    assert len(persisted) == 1


@pytest.mark.parametrize("streaming", [False, True])
async def test_expired_finalization_never_returns_success(monkeypatch, streaming):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)
    records = []

    async def persist(record):
        records.append(record)
        await asyncio.sleep(0.2)

    service = router(fake(), persist)
    results = []
    with pytest.raises(AllCandidatesFailed):
        if streaming:
            async for event in service.stream(request()):
                if isinstance(event, LLMResult):
                    results.append(event)
        else:
            results.append(await service.complete(request()))
    assert not results
    assert len(records) == 1
    assert records[0].success is False
    assert records[0].persistence_status == "unknown"


async def test_caller_cancellation_survives_a_slow_provenance_callback(monkeypatch):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)
    entered = asyncio.Event()
    records = []

    class Waiting(FakeAdapter):
        async def complete(self, candidate, llm_request):
            entered.set()
            await asyncio.Event().wait()

    async def persist(record):
        records.append(record)
        await asyncio.sleep(0.2)

    service = router(Waiting([FakeRoute(candidate=RouteCandidate(provider="remote", model="model"))]), persist)
    running = asyncio.create_task(service.complete(request()))
    await entered.wait()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert len(records) == 1
    assert records[0].persistence_status == "unknown"


async def test_stream_cleanup_finishes_inside_budget_before_canonical_result(monkeypatch):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)
    records = []
    cleaned = []

    class SlowClose(FakeAdapter):
        async def stream(self, candidate, llm_request):
            try:
                yield StreamDone(completion=AdapterCompletion(text="complete answer", provider="remote", model="model"))
            finally:
                try:
                    await asyncio.sleep(0.2)
                finally:
                    cleaned.append(True)

    service = router(SlowClose([FakeRoute(candidate=RouteCandidate(provider="remote", model="model"))]), records.append)
    results = []
    with pytest.raises(AllCandidatesFailed):
        async for event in service.stream(request()):
            if isinstance(event, LLMResult):
                results.append(event)
    assert cleaned == [True]
    assert results == [] and not records[0].success