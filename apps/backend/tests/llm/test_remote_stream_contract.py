import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, LLMResult, PoolRouter, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, StreamDelta, StreamDone
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.pools import PoolConfig
from bebshax.llm.latency import ATTEMPT_TIMEOUTS_S
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context


@pytest.fixture
async def approved_stream_policy() -> AsyncIterator[RemoteProcessingPolicy]:
    with llm_request_context(LLMRequestContext(data_classification="synthetic")):
        yield RemoteProcessingPolicy(
            policy_id="synthetic-stream-fixture", synthetic_providers=frozenset({"openrouter"}),
            synthetic_openrouter_upstreams=frozenset({"Test Endpoint"}),
        )


class Frames(httpx.AsyncByteStream):
    def __init__(self, frames):
        self.frames = frames
        self.sent = 0
        self.closed = False

    async def __aiter__(self):
        for frame in self.frames:
            self.sent += 1
            if isinstance(frame, Exception):
                raise frame
            yield frame.encode()

    async def aclose(self):
        self.closed = True


def frame(text="", finish=None):
    return "data: " + json.dumps({"model": "reported-model", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}) + "\n\n"


DONE = 'data: {"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":3}}\n\ndata: [DONE]\n\n'


def llm_request(json_mode=False):
    return LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="complete input")], json_mode=json_mode, max_output_tokens=64)


def native(frames, sent=None):
    def handler(request):
        if sent is not None:
            sent.append(json.loads(request.content))
        return httpx.Response(200, stream=frames, headers={"Content-Type": "text/event-stream"})

    return OpenRouterAdapter(
        api_key="synthetic-test-key",
        catalogue=[{
            "id": "catalog/chat:free", "context_length": 128000,
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["max_tokens", "response_format"],
        }],
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture(autouse=True)
def no_pins(monkeypatch):
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)


async def test_native_stream_delivers_first_real_text_before_terminal_and_normalizes_done():
    frames = Frames([frame(), frame("Hello"), frame(" world", "stop"), DONE])
    sent = []
    adapter = native(frames, sent)
    try:
        [candidate] = await adapter.candidates()
        stream = adapter.stream(candidate, llm_request())
        first = await anext(stream)
        assert first == StreamDelta(text="Hello")
        assert frames.sent == 2
        rest = [event async for event in stream]
        assert rest[0] == StreamDelta(text=" world")
        assert isinstance(rest[-1], StreamDone)
        assert rest[-1].completion.text == "Hello world"
        assert rest[-1].completion.model == "reported-model"
        assert rest[-1].completion.usage.output_tokens == 3
        assert sent[0]["stream"] is True
        assert sent[0]["stream_options"] == {"include_usage": True}
        assert frames.closed
    finally:
        await adapter.aclose()


async def test_structured_stream_emits_nothing_until_complete_object_is_validated():
    frames = Frames([frame('{"ok":'), frame('true}', "stop"), DONE])
    adapter = native(frames)
    try:
        [candidate] = await adapter.candidates()
        stream = adapter.stream(candidate, llm_request(json_mode=True))
        first = await anext(stream)
        assert first == StreamDelta(text='{"ok":true}')
        assert frames.sent == 3
        assert isinstance(await anext(stream), StreamDone)
        await stream.aclose()
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("frames", [
    [frame('{"partial":', "stop"), DONE],
    [frame('{"ok":true}', "length"), DONE],
    [frame('{"ok":true}', "stop")],
    ['data: not-json\n\n'],
])
async def test_partial_json_truncation_and_missing_terminal_cannot_be_accepted(frames):
    adapter = native(Frames(frames))
    output = []
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            async for event in adapter.stream(candidate, llm_request(json_mode=True)):
                output.append(event)
        assert error.value.kind == FailureKind.MALFORMED_RESPONSE
        assert output == []
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("first_text, should_fallback", [("", True), ("   ", True), ("real answer", False)])
async def test_only_nonempty_answer_text_commits_the_router(first_text, should_fallback, approved_stream_policy):
    frames = Frames([frame(first_text), 'data: {"error":{"code":503,"message":"upstream unavailable"}}\n\n'])
    adapter = native(frames)
    backup = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="backup", model="remote"), reply="fallback response")])
    records = []
    router = PoolRouter(
        {"remote": adapter, "backup": backup},
        pools={"test": PoolConfig(name="test", adapters=["remote", "backup"])},
        task_pool_map={TaskType.PERSONA_RESPONSE: "test"}, on_provenance=records.append,
        processing_policy=approved_stream_policy,
    )
    try:
        if should_fallback:
            events = [event async for event in router.stream(llm_request())]
            result = events[-1]
            assert isinstance(result, LLMResult)
            assert result.provider == "backup"
            assert backup.calls
        else:
            with pytest.raises(AttemptFailed) as error:
                _ = [event async for event in router.stream(llm_request())]
            assert error.value.kind == FailureKind.SERVER_ERROR
            assert error.value.provenance is records[0]
            assert not backup.calls
        assert frames.closed
    finally:
        await adapter.aclose()


async def test_slow_stream_handshake_is_bounded_by_the_attempt_budget(monkeypatch):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)
    adapter = native(Frames([]))
    original = adapter._client
    assert original is not None

    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, stream=Frames([frame("hello", "stop"), DONE]))

    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        [candidate] = await adapter.candidates()
        loop = asyncio.get_running_loop()
        started = loop.time()
        with pytest.raises(AttemptFailed):
            _ = [event async for event in adapter.stream(candidate, llm_request())]
        assert loop.time() - started < 0.15
    finally:
        await adapter.aclose()
        await original.aclose()


async def test_invalid_delta_type_is_not_treated_as_an_empty_heartbeat():
    bad = 'data: {"choices":[{"delta":{"content":0},"finish_reason":null}]}\n\n'
    adapter = native(Frames([bad, frame("answer", "stop"), DONE]))
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as failed:
            _ = [event async for event in adapter.stream(candidate, llm_request())]
        assert failed.value.kind == FailureKind.MALFORMED_RESPONSE
    finally:
        await adapter.aclose()


async def test_canonical_completion_cannot_disagree_with_already_visible_text():
    class Inconsistent(FakeAdapter):
        async def stream(self, candidate, request):
            yield StreamDelta(text="visible answer")
            yield StreamDone(completion=AdapterCompletion(text="different answer", provider=candidate.provider, model=candidate.model))

    primary = Inconsistent([FakeRoute(candidate=RouteCandidate(provider="primary", model="remote"))])
    secondary = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="secondary", model="remote"))])
    router = PoolRouter({"freellmpool": primary, "openrouter": secondary})
    with pytest.raises(AttemptFailed) as failed:
        _ = [event async for event in router.stream(llm_request())]
    assert failed.value.kind == FailureKind.MALFORMED_RESPONSE
    assert secondary.calls == []


async def test_stream_cleanup_is_bounded_even_when_generator_suppresses_first_cancel(monkeypatch):
    monkeypatch.setitem(ATTEMPT_TIMEOUTS_S, TaskType.PERSONA_RESPONSE, 0.02)

    class SlowClose(FakeAdapter):
        async def stream(self, candidate, request):
            try:
                yield StreamDelta(text="visible answer")
                await asyncio.sleep(1)
            finally:
                try:
                    await asyncio.sleep(0.2)
                except asyncio.CancelledError:
                    await asyncio.sleep(0.2)

    primary = SlowClose([FakeRoute(candidate=RouteCandidate(provider="primary", model="remote"))])
    router = PoolRouter({"freellmpool": primary, "openrouter": FakeAdapter([])})
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(AttemptFailed):
        _ = [event async for event in router.stream(llm_request())]
    assert loop.time() - started < 0.15