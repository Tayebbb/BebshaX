import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter, rank_free_catalogue
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context


def model_row(model="catalog/chat:free", context=128000, **changes):
    return {
        "id": model,
        "context_length": context,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["response_format", "temperature", "max_tokens"],
        **changes,
    }


def llm_request(**changes):
    return LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="Return a complete object")],
        max_output_tokens=32,
        **changes,
    )


def response_body(text='{"ok": true}', finish="stop", **changes):
    return {
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 32},
        **changes,
    }


@pytest.fixture(autouse=True)
def clear_pins(monkeypatch):
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)


def adapter_with(rows, replies, sent):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": rows})
        sent.append(json.loads(request.content))
        return replies.pop(0)

    adapter = OpenRouterAdapter(api_key="synthetic-test-key", discover_catalogue=True)
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


async def test_catalog_keeps_long_plain_route_until_request_eligibility():
    rows = [model_row(f"catalog/short-{index}:free", 8000) for index in range(5)]
    rows.append(model_row("catalog/large-plain:free", 1000000, supported_parameters=["max_tokens"]))
    sent = []
    adapter = adapter_with(rows, [httpx.Response(200, json=response_body("complete response"))], sent)
    request = llm_request().model_copy(update={"messages": [ChatMessage(role="user", content="x" * 80000)]})
    try:
        policy = RemoteProcessingPolicy(
            policy_id="synthetic-catalogue-fixture", synthetic_providers=frozenset({"openrouter"}),
            synthetic_openrouter_upstreams=frozenset({"Test Endpoint"}),
        )
        with llm_request_context(LLMRequestContext(data_classification="synthetic")):
            result = await SingleAdapterLLMService(adapter, processing_policy=policy).complete(request)
        assert result.text == "complete response"
        assert sent[0]["model"] == "catalog/large-plain:free"
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("pin", ["catalog/paid", "catalog/missing:free"])
async def test_unknown_or_paid_pins_cannot_authorize_dispatch(monkeypatch, pin):
    monkeypatch.setenv("BEBSHAX_OPENROUTER_MODELS", pin)
    adapter = adapter_with([model_row()], [], [])
    try:
        assert await adapter.candidates() == []
    finally:
        await adapter.aclose()


@pytest.mark.parametrize(
    "row",
    [
        model_row(context=None),
        model_row(context="invalid"),
        model_row(context=0),
        model_row(pricing={"prompt": "0", "completion": "0.001"}),
        model_row(pricing={}),
        model_row(pricing={"prompt": "NaN", "completion": "0"}),
    ],
)
def test_unknown_context_or_nonzero_unverified_price_fails_closed(row):
    assert rank_free_catalogue([row]) == []


async def test_json_contract_is_not_dropped_on_noncontext_400():
    sent = []
    adapter = adapter_with(
        [model_row()],
        [httpx.Response(400, json={"error": {"message": "response_format unsupported"}}),
         httpx.Response(200, json=response_body("unstructured prose"))],
        sent,
    )
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, llm_request(json_mode=True))
        assert len(sent) == 1
        assert sent[0]["response_format"] == {"type": "json_object"}
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("text", ["prose only", "[]", "42", '{"unfinished":'])
async def test_json_mode_requires_a_complete_object(text):
    adapter = adapter_with([model_row()], [httpx.Response(200, json=response_body(text))], [])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(candidate, llm_request(json_mode=True))
        assert failure.value.kind == FailureKind.MALFORMED_RESPONSE
    finally:
        await adapter.aclose()


async def test_exact_output_budget_stop_is_valid_and_missing_model_is_unknown():
    sent = []
    adapter = adapter_with([model_row()], [httpx.Response(200, json=response_body())], sent)
    try:
        [candidate] = await adapter.candidates()
        result = await adapter.complete(candidate, llm_request(json_mode=True, temperature=0.2))
        assert result.text == '{"ok": true}'
        assert result.model == "unknown"
        assert any("requested" in note for note in result.notes)
        assert sent[0]["temperature"] == 0.2 and sent[0]["max_tokens"] == 32
        assert sent[0]["provider"]["data_collection"] == "deny"
        assert sent[0]["provider"]["require_parameters"] is True
    finally:
        await adapter.aclose()


async def test_tools_without_a_tool_contract_are_rejected_before_dispatch():
    sent = []
    adapter = adapter_with([model_row()], [httpx.Response(200, json=response_body())], sent)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(candidate, llm_request(tools_required=True))
        assert failure.value.kind == FailureKind.CAPABILITY_UNSUPPORTED
        assert not sent
    finally:
        await adapter.aclose()


async def test_direct_unverified_candidate_cannot_bypass_catalogue():
    sent = []
    adapter = adapter_with([model_row()], [httpx.Response(200, json=response_body())], sent)
    try:
        with pytest.raises(AttemptFailed):
            await adapter.complete(RouteCandidate(provider="openrouter", model="catalog/paid"), llm_request())
        assert not sent
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("finish", [{}, [], 5, "unexpected-finish"])
async def test_bad_finish_metadata_is_a_classified_provider_envelope_error(finish):
    adapter = adapter_with([model_row()], [httpx.Response(200, json=response_body(finish=finish))], [])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, llm_request())
        assert error.value.kind == FailureKind.MALFORMED_RESPONSE
        assert error.value.observations[0].status_code == 200
    finally:
        await adapter.aclose()


async def test_non_success_http_attempt_retains_unknown_consumption():
    adapter = adapter_with([model_row()], [httpx.Response(429, json={"error": {"message": "limit"}})], [])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, llm_request())
        [observation] = error.value.observations
        assert observation.status_code == 429
        assert observation.outcome == "failed" and observation.consumption == "unknown"
    finally:
        await adapter.aclose()