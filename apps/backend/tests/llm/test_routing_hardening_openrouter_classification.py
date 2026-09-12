"""OpenRouter failure classification and the $0 model list.

Regressions: 402 (credits gone) and 408 fell through to PROVIDER_UNAVAILABLE;
a 400 whose body says the prompt exceeds the model's context was classified
PROVIDER_UNAVAILABLE and cooled the route for a size problem; the retry
without response_format was invisible in provenance; `openrouter/auto`
(routes to PAID models) sat in the defaults.
"""

import json

import httpx
import pytest

from bebshax.llm import AttemptFailed, ChatMessage, FailureKind, LLMRequest, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.openrouter_adapter import (
    DEFAULT_MODELS,
    OpenRouterAdapter,
    _map_http_status,
    _retry_after_hint,
)
from bebshax.llm.failures import FAILURE_POLICIES

_QUOTA_BODY = (
    '{"error":{"message":"Rate limit exceeded: free-models-per-day","code":429,'
    '"metadata":{"headers":{"X-RateLimit-Reset":"1788825600000"},"limit_source":"openrouter_free_tier_daily"}}}'
)


def test_retry_after_hint_prefers_the_header_then_the_reset_timestamp() -> None:
    assert _retry_after_hint({"Retry-After": "42"}, "") == 42.0
    # 1788825600000 ms = 2026-09-08T00:00:00Z; 1 h before that the hint is 3600 s.
    assert _retry_after_hint({}, _QUOTA_BODY, now=1788825600.0 - 3600) == 3600.0
    assert _retry_after_hint({}, _QUOTA_BODY, now=1788825600.0 + 5) is None  # already reset
    assert _retry_after_hint({}, "no hint here") is None
    assert _retry_after_hint(None, "") is None


@pytest.mark.asyncio
async def test_quota_failure_carries_the_reset_hint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text=_QUOTA_BODY, headers={"Retry-After": "1800"})

    adapter = _adapter(handler)
    with pytest.raises(AttemptFailed) as info:
        await adapter.complete(_CAND, _request())
    assert info.value.kind == FailureKind.QUOTA_EXHAUSTED
    assert info.value.retry_after_s == 1800.0

_CTX_BODY = json.dumps(
    {
        "error": {
            "message": "This endpoint's maximum context length is 8192 tokens. "
            "However, you requested about 12000 tokens (11000 of text input, 1000 in the output).",
            "code": 400,
        }
    }
)


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (429, "", FailureKind.RATE_LIMITED),
        (429, '{"error":{"message":"Rate limit exceeded: free-models-per-min"}}', FailureKind.RATE_LIMITED),
        # Upstream per-model saturation (observed live): the model's shared pool, not our key.
        (
            429,
            '{"error":{"message":"Provider returned error","code":429,"metadata":{"raw":"google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream. Please retry shortly","limit_source":"upstream_provider_shared_pool"}}}',
            FailureKind.MODEL_UNAVAILABLE,
        ),
        (402, '{"error":{"message":"Insufficient credits"}}', FailureKind.QUOTA_EXHAUSTED),
        # The account's free-tier day cap (observed live after ~50 calls): a quota, not a burst.
        (
            429,
            '{"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day","code":429,"metadata":{"headers":{"X-RateLimit-Limit":"50","X-RateLimit-Remaining":"0","X-RateLimit-Reset":"1788825600000"},"limit_source":"openrouter_free_tier_daily"}}}',
            FailureKind.QUOTA_EXHAUSTED,
        ),
        (408, "", FailureKind.TIMEOUT),
        (401, "", FailureKind.AUTH_INVALID),
        (403, "", FailureKind.AUTH_INVALID),
        (404, "", FailureKind.MODEL_UNAVAILABLE),
        (400, _CTX_BODY, FailureKind.CONTEXT_WINDOW_EXCEEDED),
        (400, "Prompt is too long for this model", FailureKind.CONTEXT_WINDOW_EXCEEDED),
        (400, "Request exceeds the TOKEN LIMIT", FailureKind.CONTEXT_WINDOW_EXCEEDED),
        (413, "Payload Too Large: maximum tokens exceeded", FailureKind.CONTEXT_WINDOW_EXCEEDED),
        (400, '{"error":{"message":"response_format is not supported"}}', FailureKind.CAPABILITY_UNSUPPORTED),
        (413, "", FailureKind.CONTEXT_WINDOW_EXCEEDED),
        (500, "", FailureKind.SERVER_ERROR),
        (503, "", FailureKind.SERVER_ERROR),
        (None, "", FailureKind.PROVIDER_UNAVAILABLE),
    ],
)
def test_status_and_body_map_to_kind(status, body, expected) -> None:
    assert _map_http_status(status, body) == expected


def test_context_overflow_policy_advances_without_cooldown() -> None:
    policy = FAILURE_POLICIES[FailureKind.CONTEXT_WINDOW_EXCEEDED]
    assert policy.try_next_candidate and not policy.cooldown_route


def test_default_models_are_free_only() -> None:
    assert "openrouter/auto" not in DEFAULT_MODELS
    assert DEFAULT_MODELS and all(m.endswith(":free") for m in DEFAULT_MODELS)


def _adapter(handler) -> OpenRouterAdapter:
    adapter = OpenRouterAdapter(api_key="test-key-not-real", catalogue=[{
        "id": "some/model:free", "context_length": 8192,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["response_format", "max_tokens"],
    }])
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


_CAND = RouteCandidate(provider="openrouter", model="some/model:free", context_window=8192)


def _request(json_mode: bool = False) -> LLMRequest:
    return LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content="hello")],
        json_mode=json_mode,
        max_output_tokens=200,
    )


async def test_context_overflow_400_is_not_retried_and_classified() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(400, content=_CTX_BODY.encode())

    with pytest.raises(AttemptFailed) as exc:
        await _adapter(handler).complete(_CAND, _request(json_mode=True))
    assert exc.value.kind == FailureKind.CONTEXT_WINDOW_EXCEEDED
    assert len(calls) == 1  # dropping response_format cannot shrink the prompt — no retry


async def test_402_is_quota_exhausted_end_to_end() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    with pytest.raises(AttemptFailed) as exc:
        await _adapter(handler).complete(_CAND, _request())
    assert exc.value.kind == FailureKind.QUOTA_EXHAUSTED
    assert FAILURE_POLICIES[exc.value.kind].cooldown_scope == "provider"


async def test_unsupported_response_format_is_not_silently_dropped() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if "response_format" in payload:
            return httpx.Response(
                400, json={"error": {"message": "response_format is not supported by this model"}}
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4},
                "model": "some/model:free",
            },
        )

    with pytest.raises(AttemptFailed) as failure:
        await _adapter(handler).complete(_CAND, _request(json_mode=True))
    assert failure.value.kind == FailureKind.CAPABILITY_UNSUPPORTED
    assert len(calls) == 1 and "response_format" in calls[0]


async def test_clean_success_has_no_degradation_note() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1},
                "model": "some/model:free",
            },
        )

    completion = await _adapter(handler).complete(_CAND, _request(json_mode=True))
    assert not any("response_format dropped" in note for note in completion.notes)
