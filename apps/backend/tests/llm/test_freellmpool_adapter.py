"""FreellmpoolAdapter unit tests with a stub pool — no network involved."""

import httpx
import pytest
from freellmpool import Reply
from freellmpool import errors as fl_errors

from bebshax.llm import AttemptFailed, ChatMessage, FailureKind, LLMRequest, TaskType
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter


class StubPool:
    def __init__(self, outcome) -> None:
        self._outcome = outcome
        self.calls: list[dict] = []

    async def achat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def aclose(self) -> None:
        pass


def _reply(text="hello", provider_id="groq", model="llama-3.3-70b", **kw) -> Reply:
    return Reply(
        text=text,
        provider_id=provider_id,
        model=model,
        raw={},
        prompt_tokens=kw.get("prompt_tokens", 10),
        completion_tokens=kw.get("completion_tokens", 5),
        attempts=kw.get("attempts", 2),
        cached=kw.get("cached", False),
    )


def _request(**kwargs) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[
            ChatMessage(role="system", content="be brief"),
            ChatMessage(role="user", content="hi"),
        ],
        **kwargs,
    )


async def _complete(outcome, request=None):
    adapter = FreellmpoolAdapter(pool=StubPool(outcome))
    [candidate] = await adapter.candidates()
    return adapter, await adapter.complete(candidate, request or _request())


async def _expect_failure(outcome, expected_kind: FailureKind) -> None:
    adapter = FreellmpoolAdapter(pool=StubPool(outcome))
    [candidate] = await adapter.candidates()
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(candidate, _request())
    assert exc.value.kind == expected_kind


async def test_success_records_concrete_provider_model_and_notes() -> None:
    _, completion = await _complete(_reply())
    assert completion.provider == "groq"  # not "freellmpool/auto"
    assert completion.model == "llama-3.3-70b"
    assert completion.usage.input_tokens == 10 and completion.usage.output_tokens == 5
    assert any("internal attempts: 2" in n for n in completion.notes)


async def test_request_parameters_are_passed_through() -> None:
    adapter = FreellmpoolAdapter(pool=StubPool(_reply()))
    [candidate] = await adapter.candidates()
    await adapter.complete(candidate, _request(max_output_tokens=64, temperature=0.7))
    call = adapter._pool.calls[0]
    assert call["max_tokens"] == 64
    assert call["temperature"] == 0.7
    assert call["messages"][0] == {"role": "system", "content": "be brief"}


async def test_per_task_attempt_timeout_is_passed() -> None:
    from bebshax.llm.latency import attempt_timeout_s

    adapter = FreellmpoolAdapter(pool=StubPool(_reply()))
    [candidate] = await adapter.candidates()
    await adapter.complete(candidate, _request())  # PERSONA_RESPONSE = interactive
    call = adapter._pool.calls[0]
    assert call["timeout"] == attempt_timeout_s(TaskType.PERSONA_RESPONSE)
    assert call["timeout"] <= 30


async def test_context_window_exceeded_maps_to_our_kind() -> None:
    await _expect_failure(
        fl_errors.ContextWindowExceeded([("groq", "llama")], est_tokens=999_999),
        FailureKind.CONTEXT_WINDOW_EXCEEDED,
    )


async def test_all_providers_exhausted_maps_to_provider_unavailable() -> None:
    await _expect_failure(
        fl_errors.AllProvidersExhausted([("groq", "llama")]),
        FailureKind.PROVIDER_UNAVAILABLE,
    )


async def test_exhausted_with_429_client_status_maps_to_rate_limited() -> None:
    await _expect_failure(
        fl_errors.AllProvidersExhausted([("groq", "llama")], client_status=429),
        FailureKind.RATE_LIMITED,
    )


async def test_provider_http_errors_map_by_status() -> None:
    await _expect_failure(
        fl_errors.ProviderHTTPError(503, "down", retryable=True), FailureKind.SERVER_ERROR
    )
    await _expect_failure(
        fl_errors.ProviderHTTPError(401, "bad key", retryable=False), FailureKind.AUTH_INVALID
    )
    await _expect_failure(
        fl_errors.ProviderHTTPError(404, "gone", retryable=False), FailureKind.MODEL_UNAVAILABLE
    )


async def test_timeout_and_connection_errors_map() -> None:
    await _expect_failure(httpx.ReadTimeout("slow"), FailureKind.TIMEOUT)
    await _expect_failure(httpx.ConnectError("refused"), FailureKind.CONNECTION)


async def test_empty_reply_is_malformed_response() -> None:
    await _expect_failure(_reply(text="   "), FailureKind.MALFORMED_RESPONSE)


async def test_cached_reply_is_noted_in_completion() -> None:
    """Brief acceptance: cache hits are visible in provenance, never silent."""
    _, completion = await _complete(_reply(cached=True))
    assert any("served from freellmpool response cache" in n for n in completion.notes)


async def test_truncated_reply_is_malformed_response() -> None:
    """completion_tokens >= max_output_tokens ⇒ output was cut mid-thought."""
    adapter = FreellmpoolAdapter(pool=StubPool(_reply(completion_tokens=64)))
    [candidate] = await adapter.candidates()
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(candidate, _request(max_output_tokens=64))
    assert exc.value.kind == FailureKind.MALFORMED_RESPONSE
    assert "truncated" in exc.value.detail


async def test_reply_under_budget_is_not_truncated() -> None:
    _, completion = await _complete(
        _reply(completion_tokens=63), _request(max_output_tokens=64)
    )
    assert completion.text == "hello"


async def test_no_budget_means_no_truncation_check() -> None:
    _, completion = await _complete(_reply(completion_tokens=5000), _request())
    assert completion.text == "hello"
