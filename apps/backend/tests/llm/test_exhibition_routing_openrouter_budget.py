import asyncio
import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, TaskType
from bebshax.llm.adapters import openrouter_adapter
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.openrouter_adapter import (
    OpenRouterAdapter,
)
from bebshax.llm.failures import AttemptFailed, FailureKind


ATTEMPT_BUDGET_S = 12.5
CANDIDATE = RouteCandidate(provider="openrouter", model="synthetic/model:free")
CATALOGUE = [{"id": CANDIDATE.model, "context_length": 128000, "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["response_format", "max_tokens"]}]


@pytest.fixture
async def budget_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    loop = asyncio.get_running_loop()
    now = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: now[0])
    monkeypatch.setattr(openrouter_adapter, "remaining_attempt_timeout_s", lambda task: ATTEMPT_BUDGET_S)
    return now


def _request() -> LLMRequest:
    return LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content="Preserve this synthetic persona and evidence."),
            ChatMessage(role="user", content="Return a JSON reply."),
        ],
        json_mode=True,
    )


def _success() -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})


async def test_unsupported_response_format_is_not_retried_with_a_weaker_contract(
    budget_clock: list[float],
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            budget_clock[0] += 8.0
            return httpx.Response(400, text="response_format is not supported")
        return _success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client

        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(CANDIDATE, _request())

    assert failure.value.kind == FailureKind.CAPABILITY_UNSUPPORTED
    assert len(calls) == 1
    assert calls[0].extensions["timeout"]["read"] == ATTEMPT_BUDGET_S
    assert json.loads(calls[0].content)["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("elapsed", [ATTEMPT_BUDGET_S, ATTEMPT_BUDGET_S + 1.0])
async def test_response_format_retry_is_not_sent_after_the_attempt_budget_is_spent(
    budget_clock: list[float], elapsed: float,
) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            budget_clock[0] += elapsed
            return httpx.Response(400, text="response_format is not supported")
        return _success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client

        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(CANDIDATE, _request())

    assert failure.value.kind == FailureKind.TIMEOUT
    assert failure.value.detail == "attempt budget exceeded"
    assert len(calls) == 1


async def test_entire_attempt_deadline_cancels_an_inflight_post(
    budget_clock: list[float],
) -> None:
    loop = asyncio.get_running_loop()
    started = budget_clock[0]
    calls = []
    cancelled = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        released = loop.create_future()

        def release_unbounded_request() -> None:
            if not released.done():
                released.set_result(None)

        budget_clock[0] = started + ATTEMPT_BUDGET_S + 0.5
        loop.call_soon(loop.call_soon, release_unbounded_request)
        try:
            await released
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return _success()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture", catalogue=CATALOGUE)
        adapter._client = client

        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(CANDIDATE, _request())

    assert failure.value.kind == FailureKind.TIMEOUT
    assert failure.value.detail == "attempt budget exceeded"
    assert cancelled == [True]
    assert len(calls) == 1