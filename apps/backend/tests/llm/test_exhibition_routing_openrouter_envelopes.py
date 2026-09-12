import json
from collections.abc import AsyncIterator

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, PoolConfig, PoolRouter, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

CATALOGUE = [{"id": "synthetic/model:free", "context_length": 128000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["response_format", "max_tokens"]}]


@pytest.fixture(autouse=True)
async def _trusted_synthetic_context() -> AsyncIterator[None]:
    with llm_request_context(LLMRequestContext(data_classification="synthetic")):
        yield


@pytest.fixture(autouse=True)
def _pin_offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEBSHAX_OPENROUTER_MODELS", "synthetic/model:free")


def _request() -> LLMRequest:
    return LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="Synthetic envelope check")],
    )


def _router(adapter: OpenRouterAdapter) -> tuple[PoolRouter, FakeAdapter]:
    fallback = FakeAdapter(
        [FakeRoute(RouteCandidate(provider="fixture-secondary", model="synthetic-model"))]
    )
    return (
        PoolRouter(
            {"openrouter": adapter, "fallback": fallback},
            pools={"test": PoolConfig(name="test", adapters=["openrouter", "fallback"])},
            task_pool_map={TaskType.STRUCTURED_OUTPUT: "test"},
            processing_policy=RemoteProcessingPolicy(
                policy_id="synthetic-envelope-fixture",
                synthetic_providers=frozenset({"openrouter"}),
                synthetic_openrouter_upstreams=frozenset({"fixture-upstream"}),
            ),
        ),
        fallback,
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "not an object",
        {"choices": None},
        {"choices": []},
        {"choices": {"message": {"content": "wrong container"}}},
        {"choices": [None]},
        {"choices": ["not a choice"]},
        {"choices": [{"message": None}]},
        {"choices": [{"message": []}]},
        {"choices": [{"message": "not a message"}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": 42}}]},
        {"choices": [{"message": {"content": ["not text"]}}]},
        {"choices": [{"message": {"content": "   "}}]},
        {"choices": [{"message": {"content": "ok"}}], "usage": None},
        {"choices": [{"message": {"content": "ok"}}], "usage": []},
        {"choices": [{"message": {"content": "ok"}}], "usage": "not usage"},
        {
            "choices": [{"message": {"content": ""}}],
            "usage": {"completion_tokens_details": ["not details"]},
        },
        {
            "choices": [{"message": {"content": ""}}],
            "usage": {"completion_tokens_details": "not details"},
        },
    ],
    ids=[
        "null-root", "array-root", "string-root", "null-choices", "empty-choices",
        "object-choices", "null-choice", "string-choice", "null-message",
        "array-message", "string-message", "null-content", "numeric-content",
        "array-content", "blank-content", "null-usage", "array-usage", "string-usage",
        "array-reasoning-details", "string-reasoning-details",
    ],
)
async def test_invalid_openrouter_envelope_is_malformed_and_allows_fallback(
    payload: object,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=json.dumps(payload).encode("utf-8"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client
        router, fallback = _router(adapter)

        result = await router.complete(_request())

    assert result.provider == "fixture-secondary"
    assert len(calls) == 2
    assert fallback.calls == ["fixture-secondary/synthetic-model"]
    assert [attempt.failure_kind for attempt in result.provenance.attempts] == [
        FailureKind.MALFORMED_RESPONSE,
        FailureKind.MALFORMED_RESPONSE,
        None,
    ]


async def test_openrouter_decoder_code_error_is_internal_and_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    def broken_json() -> object:
        raise AttributeError("synthetic decoder implementation fault")

    monkeypatch.setattr(response, "json", broken_json)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response)
    ) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client
        router, fallback = _router(adapter)

        with pytest.raises(AttemptFailed) as failure:
            await router.complete(_request())

    assert failure.value.kind == FailureKind.INTERNAL_ERROR
    assert fallback.calls == []


async def test_minimal_valid_openrouter_envelope_returns_text_without_fallback() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "accepted"}}]}
            )
        )
    ) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client
        router, fallback = _router(adapter)

        result = await router.complete(_request())

    assert result.provider == "openrouter"
    assert result.model == "unknown"
    assert result.text == "accepted"
    assert result.usage.input_tokens is None and result.usage.output_tokens is None
    assert fallback.calls == []