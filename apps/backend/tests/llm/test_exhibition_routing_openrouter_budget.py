import asyncio
import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, TaskType
from bebshax.llm.adapters import openrouter_adapter
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.openrouter_adapter import (
    RESPONSE_FORMAT_DROPPED_NOTE,
    OpenRouterAdapter,
)
from bebshax.llm.failures import AttemptFailed, FailureKind


ATTEMPT_BUDGET_S = 12.5
CANDIDATE = RouteCandidate(provider="openrouter", model="synthetic/model:free")


@pytest.fixture
async def budget_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    loop = asyncio.get_running_loop()
    now = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: now[0])
    monkeypatch.setattr(openrouter_adapter, "attempt_timeout_s", lambda task: ATTEMPT_BUDGET_S)
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


async def test_response_format_retry_receives_only_the_remaining_attempt_budget(
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
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture")
        adapter._client = client

        completion = await adapter.complete(CANDIDATE, _request())

    assert len(calls) == 2
    assert calls[0].extensions["timeout"]["read"] == ATTEMPT_BUDGET_S
    assert calls[1].extensions["timeout"] == {
        "connect": 4.5, "read": 4.5, "write": 4.5, "pool": 4.5,
    }
    first_payload, retry_payload = [json.loads(request.content) for request in calls]
    assert retry_payload == {
        key: value for key, value in first_payload.items() if key != "response_format"
    }
    assert RESPONSE_FORMAT_DROPPED_NOTE in completion.notes


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
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture")
        adapter._client = client

        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(CANDIDATE, _request())

    assert failure.value.kind == FailureKind.TIMEOUT
    assert failure.value.detail == "attempt budget exceeded"
    assert len(calls) == 1


@pytest.mark.parametrize("retry", [False, True], ids=["first-post", "retry-post"])
async def test_entire_attempt_deadline_cancels_an_inflight_post(
    budget_clock: list[float], retry: bool,
) -> None:
    loop = asyncio.get_running_loop()
    started = budget_clock[0]
    calls = []
    cancelled = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if retry and len(calls) == 1:
            budget_clock[0] += 8.0
            return httpx.Response(400, text="response_format is not supported")
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
        adapter = OpenRouterAdapter(api_key="unused-offline-fixture")
        adapter._client = client

        with pytest.raises(AttemptFailed) as failure:
            await adapter.complete(CANDIDATE, _request())

    assert failure.value.kind == FailureKind.TIMEOUT
    assert failure.value.detail == "attempt budget exceeded"
    assert cancelled == [True]
    assert len(calls) == (2 if retry else 1)