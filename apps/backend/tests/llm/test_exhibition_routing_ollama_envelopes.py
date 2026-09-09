import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.base import RouteCandidate, StreamDelta
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.pools import PoolConfig
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.types import LLMResult


def _request() -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,
        messages=[ChatMessage(role="user", content="Synthetic stream check")],
    )


def _transport(
    response: httpx.Response | Exception, calls: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "llama3.2:3b", "size": 1000}]}
            )
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"model_info": {"llama.context_length": 8192}})
        assert request.url.path == "/api/chat"
        calls.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    return httpx.MockTransport(handler)


def _router(
    client: httpx.AsyncClient, records: list[ProvenanceRecord]
) -> tuple[PoolRouter, FakeAdapter]:
    fallback = FakeAdapter(
        [FakeRoute(RouteCandidate(provider="fake", model="fallback-model"))]
    )
    return (
        PoolRouter(
            {"ollama": OllamaAdapter(client=client), "fallback": fallback},
            pools={
                "streaming": PoolConfig(
                    name="streaming", adapters=["ollama", "fallback"], max_concurrency=2
                )
            },
            task_pool_map={TaskType.PERSONA_INTERVIEW: "streaming"},
            on_provenance=records.append,
        ),
        fallback,
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        [{}],
        "not an object",
        42,
        {"message": ["not a message"], "done": True},
        {"message": "not a message", "done": True},
        {"message": {"content": 42}, "done": True},
        {"message": {"content": ["not text"]}, "done": True},
        {"message": {"content": None}, "done": True},
        {"message": None, "done": True},
    ],
    ids=[
        "null-root", "empty-array-root", "array-root", "string-root", "numeric-root",
        "array-message", "string-message", "numeric-content", "array-content",
        "null-content", "null-message",
    ],
)
async def test_invalid_ollama_frame_before_text_is_malformed_and_allows_fallback(
    payload: object,
) -> None:
    calls = []
    records = []
    response = httpx.Response(200, text=json.dumps(payload) + "\n")
    async with httpx.AsyncClient(
        base_url="http://ollama.test", transport=_transport(response, calls)
    ) as client:
        router, fallback = _router(client, records)

        events = [event async for event in router.stream(_request())]

    assert isinstance(events[-1], LLMResult)
    assert events[-1].provider == "fake"
    assert len(calls) == 2
    assert fallback.calls == ["fake/fallback-model"]
    assert [attempt.failure_kind for attempt in records[-1].attempts] == [
        FailureKind.MALFORMED_RESPONSE,
        FailureKind.MALFORMED_RESPONSE,
        None,
    ]


@pytest.mark.parametrize("payload", [None, []], ids=["null-root", "array-root"])
async def test_invalid_ollama_frame_after_text_surfaces_without_retry_or_fallback(
    payload: object,
) -> None:
    calls = []
    records = []
    body = "\n".join(
        json.dumps(frame)
        for frame in [{"message": {"content": "partial reply"}, "done": False}, payload]
    )
    async with httpx.AsyncClient(
        base_url="http://ollama.test",
        transport=_transport(httpx.Response(200, text=body), calls),
    ) as client:
        router, fallback = _router(client, records)
        received = []

        with pytest.raises(AttemptFailed) as failure:
            async for event in router.stream(_request()):
                if isinstance(event, StreamDelta):
                    received.append(event.text)

    assert failure.value.kind == FailureKind.MALFORMED_RESPONSE
    assert received == ["partial reply"]
    assert len(calls) == 1
    assert fallback.calls == []
    assert not records[-1].success
    assert records[-1].attempts[-1].failure_kind == FailureKind.MALFORMED_RESPONSE


async def test_ollama_transport_code_error_is_internal_and_never_falls_back() -> None:
    calls = []
    records = []
    async with httpx.AsyncClient(
        base_url="http://ollama.test",
        transport=_transport(AttributeError("synthetic transport implementation fault"), calls),
    ) as client:
        router, fallback = _router(client, records)

        with pytest.raises(AttemptFailed) as failure:
            _ = [event async for event in router.stream(_request())]

    assert failure.value.kind == FailureKind.INTERNAL_ERROR
    assert len(calls) == 1
    assert fallback.calls == []
    assert records[-1].attempts[-1].failure_kind == FailureKind.INTERNAL_ERROR


async def test_ollama_terminal_metadata_frame_without_message_preserves_text_and_usage() -> None:
    calls = []
    records = []
    body = "\n".join(
        json.dumps(frame)
        for frame in [
            {"message": {"content": "complete reply"}, "done": False},
            {"done": True, "prompt_eval_count": 7, "eval_count": 3},
        ]
    )
    async with httpx.AsyncClient(
        base_url="http://ollama.test",
        transport=_transport(httpx.Response(200, text=body), calls),
    ) as client:
        router, fallback = _router(client, records)

        events = [event async for event in router.stream(_request())]

    assert isinstance(events[-1], LLMResult)
    assert events[-1].text == "complete reply"
    assert events[-1].usage.input_tokens == 7
    assert events[-1].usage.output_tokens == 3
    assert len(calls) == 1
    assert fallback.calls == []