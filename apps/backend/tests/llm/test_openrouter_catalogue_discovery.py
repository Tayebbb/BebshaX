"""OpenRouter free-catalogue discovery.

Observed live (2026-09-08): all three hard-coded ``:free`` seeds 404'd — the
free catalogue had drifted and every request paid three dead attempts (and
three 60 s cooldowns) before reaching a working route. Production now discovers
the current free chat models from the public catalogue; the seed list is only
the offline fallback and an operator pin still wins.
"""

import json

import httpx
import pytest

from bebshax.llm.adapters.openrouter_adapter import (
    CATALOGUE_MAX_MODELS,
    DEFAULT_MODELS,
    OPENROUTER_MODELS_ENDPOINT,
    OpenRouterAdapter,
    rank_free_catalogue,
)

_CATALOGUE = [
    {"id": "acme/paid-model", "context_length": 200_000, "supported_parameters": ["response_format"]},
    {"id": "acme/safety-classifier:free", "context_length": 128_000, "supported_parameters": []},
    {"id": "acme/deep-reasoning-r1:free", "context_length": 256_000, "supported_parameters": ["response_format"]},
    {"id": "acme/coder-7b:free", "context_length": 64_000, "supported_parameters": ["response_format"]},
    {"id": "acme/chat-small:free", "context_length": 32_000, "supported_parameters": ["response_format", "tools"]},
    {"id": "acme/chat-large:free", "context_length": 262_144, "supported_parameters": ["response_format"]},
    {"id": "acme/chat-plain:free", "context_length": 1_000_000, "supported_parameters": ["tools"]},
    {"id": "acme/chat-mid:free", "context_length": 128_000, "supported_parameters": ["response_format"]},
    {"id": "acme/chat-extra:free", "context_length": 8_000, "supported_parameters": ["response_format"]},
]


def test_ranking_keeps_free_chat_models_and_prefers_structured_output() -> None:
    ranked = [row["id"] for row in rank_free_catalogue(_CATALOGUE)]
    assert len(ranked) == CATALOGUE_MAX_MODELS
    # response_format-capable first, larger context first; JSON-less route last.
    assert ranked == ["acme/chat-large:free", "acme/chat-mid:free", "acme/chat-small:free", "acme/chat-extra:free"]
    for excluded in ("acme/paid-model", "acme/safety-classifier:free", "acme/deep-reasoning-r1:free", "acme/coder-7b:free"):
        assert excluded not in ranked


def test_ranking_falls_back_to_plain_routes_when_nothing_supports_json() -> None:
    rows = [{"id": "x/plain:free", "context_length": 1000, "supported_parameters": []}]
    assert [r["id"] for r in rank_free_catalogue(rows)] == ["x/plain:free"]


def _adapter(handler, **kwargs) -> OpenRouterAdapter:
    adapter = OpenRouterAdapter(api_key="test-key-not-real", discover_catalogue=True, **kwargs)
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


@pytest.mark.asyncio
async def test_candidates_come_from_the_live_catalogue(monkeypatch) -> None:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert str(request.url) == OPENROUTER_MODELS_ENDPOINT
        return httpx.Response(200, json={"data": _CATALOGUE})

    adapter = _adapter(handler)
    cands = await adapter.candidates()
    assert [c.model for c in cands] == ["acme/chat-large:free", "acme/chat-mid:free", "acme/chat-small:free", "acme/chat-extra:free"]
    large = cands[0]
    assert large.context_window == 262_144 and large.supports_json is True and large.supports_tools is False
    assert cands[2].supports_tools is True
    # Cached: a second call does not refetch inside the TTL.
    await adapter.candidates()
    assert len(calls) == 1
    status = adapter.catalogue_status()
    assert status["discovery_enabled"] and status["error"] is None and len(status["discovered"]) == 4


@pytest.mark.asyncio
async def test_catalogue_failure_degrades_to_the_seed_list_and_is_reported(monkeypatch) -> None:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    adapter = _adapter(handler)
    assert [c.model for c in await adapter.candidates()] == DEFAULT_MODELS
    assert "HTTPStatusError" in (adapter.catalogue_status()["error"] or "")


@pytest.mark.asyncio
async def test_operator_pin_beats_discovery(monkeypatch) -> None:
    monkeypatch.setenv("BEBSHAX_OPENROUTER_MODELS", "pinned/one:free")

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("catalogue must not be fetched when models are pinned")

    adapter = _adapter(handler)
    assert [c.model for c in await adapter.candidates()] == ["pinned/one:free"]


@pytest.mark.asyncio
async def test_discovery_is_off_by_default_so_tests_stay_offline(monkeypatch) -> None:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("no network without discover_catalogue=True")

    adapter = OpenRouterAdapter(api_key="test-key-not-real")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert [c.model for c in await adapter.candidates()] == DEFAULT_MODELS


@pytest.mark.asyncio
async def test_expired_cache_refreshes_and_keeps_last_good_on_failure(monkeypatch) -> None:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    responses = [httpx.Response(200, json={"data": _CATALOGUE[:6]}), httpx.Response(500, text="boom")]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    adapter = _adapter(handler, catalogue_ttl_s=0.0)  # every call is a refresh
    first = [c.model for c in await adapter.candidates()]
    assert first == ["acme/chat-large:free", "acme/chat-small:free"]
    second = [c.model for c in await adapter.candidates()]  # refresh fails → last good catalogue
    assert second == first
    assert adapter.catalogue_status()["error"]
    assert json.dumps(adapter.catalogue_status())  # serialisable for /api/health


# ---------------------------------------------------------------------------
# Reasoning toggle. Observed live: a free reasoning model answered a 220-token
# JSON request with content "" after 254 reasoning tokens (finish_reason=length);
# with `reasoning: {enabled: false}` the same model answered in 0 reasoning
# tokens. Routes that expose the toggle get it; the empty-reply case explains
# itself in provenance.
# ---------------------------------------------------------------------------

_REASONING_CATALOGUE = [
    {"id": "acme/thinker-chat:free", "context_length": 100_000, "supported_parameters": ["response_format", "reasoning", "include_reasoning"]},
    {"id": "acme/plain-chat:free", "context_length": 50_000, "supported_parameters": ["response_format"]},
]


def _request(json_mode: bool = True):
    from bebshax.llm import ChatMessage, LLMRequest, TaskType

    return LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="hi")],
        json_mode=json_mode,
        max_output_tokens=220,
    )


def _ok_body(content: str = '{"ok": true}') -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 7}, "model": "acme/x"}


@pytest.mark.asyncio
async def test_reasoning_is_disabled_only_for_routes_that_expose_the_toggle(monkeypatch) -> None:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == OPENROUTER_MODELS_ENDPOINT:
            return httpx.Response(200, json={"data": _REASONING_CATALOGUE})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=_ok_body())

    adapter = _adapter(handler)
    thinker, plain = await adapter.candidates()
    await adapter.complete(thinker, _request())
    await adapter.complete(plain, _request())
    assert sent[0]["reasoning"] == {"enabled": False}
    assert "reasoning" not in sent[1]


@pytest.mark.asyncio
async def test_empty_reply_after_reasoning_is_explained_in_the_failure() -> None:
    from bebshax.llm import AttemptFailed, FailureKind
    from bebshax.llm.adapters.base import RouteCandidate

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "", "reasoning": "First, the user said..."}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 26, "completion_tokens": 220, "completion_tokens_details": {"reasoning_tokens": 254}},
            },
        )

    adapter = OpenRouterAdapter(api_key="test-key-not-real")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AttemptFailed) as info:
        await adapter.complete(RouteCandidate(provider="openrouter", model="acme/thinker:free"), _request())
    assert info.value.kind == FailureKind.MALFORMED_RESPONSE
    assert "254 reasoning tokens" in info.value.detail and "finish_reason=length" in info.value.detail
