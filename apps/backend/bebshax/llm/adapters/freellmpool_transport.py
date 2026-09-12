"""Request guards around Freellmpool's supported async transport/event hooks."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx
from freellmpool.client import HTTPResult
from freellmpool.errors import ProviderHTTPError
from freellmpool.models import Provider
from freellmpool.quota import QuotaStore
from freellmpool.router import Pool

from bebshax.llm.adapters.openrouter_adapter import _map_http_status
from bebshax.llm.estimator import DEFAULT_EXPECTED_OUTPUT_TOKENS, estimate_request_tokens
from bebshax.llm.failures import FAILURE_POLICIES, AttemptFailed, FailureKind
from bebshax.llm.governance import get_dispatch_approval
from bebshax.llm.latency import DeadlineExpired, await_before
from bebshax.llm.provenance import ProviderObservation
from bebshax.llm.retry import retry_after_hint
from bebshax.llm.types import LLMRequest
from bebshax.llm.validation import validate_text, validated_usage


@dataclass
class DispatchState:
    request: LLMRequest
    deadline: float
    target: str | None = None
    observations: list[ProviderObservation] = field(default_factory=list)


dispatch_state: ContextVar[DispatchState | None] = ContextVar("freellmpool_dispatch", default=None)


class DispatchAborted(BaseException):
    """Escape the SDK's broad Exception handler without blaming a provider."""

    def __init__(self, failure: AttemptFailed):
        self.failure = failure


class AttemptQuota:
    """Quota-store facade: reserve real attempts; suppress SDK success double-counts."""

    def __init__(self, store: QuotaStore, *, account_on_success: bool = True):
        self._store = store
        self._lock = threading.Lock()
        self._account_on_success = account_on_success

    def __getattr__(self, name):
        return getattr(self._store, name)

    def used(self, provider: str, model: str) -> int:
        return self._store.used(provider, model)

    def over_budget(self, provider: str, model: str, rpd: int) -> bool:
        return self._store.over_budget(provider, model, rpd)

    def reserve(self, provider: str, model: str, rpd: int) -> bool:
        with self._lock:
            if self._store.over_budget(provider, model, rpd):
                return False
            self._store.record(provider, model)
            return True

    def record(self, provider: str, model: str, n: int = 1) -> int:
        if not self._account_on_success or dispatch_state.get() is not None:
            return self.used(provider, model)
        return self._store.record(provider, model, n)


class GovernedTransport:
    def __init__(
        self, providers: list[Provider], *, apost=None,
        clock: Callable[[], float] = time.monotonic,
        quota_remaining: Callable[[str], float] | None = None,
        initial_cooldowns: dict[tuple[str, str], float] | None = None,
        on_cooldown_change: Callable[[str, str, float], None] | None = None,
        json_models: frozenset[tuple[str, str]] | None = None,
        reserve_attempt: Callable[[str], str | None] | None = None,
    ) -> None:
        self.providers = {provider.id: provider for provider in providers}
        self.pool: Pool | None = None
        self._apost = apost
        self._clock = clock
        self._client: httpx.AsyncClient | None = None
        self._cooldowns: dict[tuple[str, str], float] = dict(initial_cooldowns or {})
        self._quota_remaining = quota_remaining
        self._on_cooldown_change = on_cooldown_change
        self._json_models = json_models or frozenset()
        self._reserve_attempt = reserve_attempt

    def on_event(self, event: dict) -> None:
        state = dispatch_state.get()
        if state is not None and event.get("event") == "attempt":
            state.target = event.get("target")

    def cooling_remaining(self, provider: str, model: str) -> float:
        now = self._clock()
        sdk = self.pool.cooldown_snapshot(now).get(provider, 0.0) if self.pool is not None else 0.0
        return max(sdk, self._cooldowns.get((provider, "*"), now) - now, self._cooldowns.get((provider, model), now) - now, 0.0)

    def _cool(self, observation: ProviderObservation) -> None:
        if observation.failure_kind is None:
            return
        policy = FAILURE_POLICIES[observation.failure_kind]
        if policy.cooldown_route:
            model = "*" if policy.cooldown_scope == "provider" else observation.requested_model
            key = (observation.provider, model)
            seconds = max(policy.cooldown_seconds or 60.0, observation.retry_after_s or 0.0)
            now = self._clock()
            until = max(self._cooldowns.get(key, 0.0), now + seconds)
            self._cooldowns[key] = until
            if self._on_cooldown_change is not None:
                try:
                    self._on_cooldown_change(observation.provider, model, until - now)
                except Exception as exc:
                    state = dispatch_state.get()
                    raise DispatchAborted(AttemptFailed(
                        FailureKind.INTERNAL_ERROR, observation.provider, observation.requested_model,
                        "cooldown persistence callback failed", provider_fault=False,
                        observations=state.observations if state is not None else [observation],
                    )) from exc

    async def _post(self, url: str, headers: dict, body: dict, timeout: float) -> HTTPResult:
        if self._apost is not None:
            return await self._apost(url, headers, body, timeout)
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
        async with self._client.stream("POST", url, headers=headers, json=body, timeout=httpx.Timeout(timeout, connect=min(10.0, timeout))) as response:
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > 32 * 1024 * 1024:
                    raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, "freellmpool", "auto", "provider response exceeds byte limit")
            text = bytes(chunks).decode("utf-8", "replace")
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = {}
            return HTTPResult(response.status_code, parsed, text, dict(response.headers))

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def post(self, url: str, headers: dict, body: dict, timeout: float) -> HTTPResult:
        state = dispatch_state.get()
        if state is None or not state.target:
            raise DispatchAborted(AttemptFailed(FailureKind.INTERNAL_ERROR, "freellmpool", "auto", "missing governed dispatch context", provider_fault=False))
        provider_id, _, model_name = state.target.partition("/")
        provider = self.providers.get(provider_id)
        model = provider.model(model_name) if provider else None
        observation = ProviderObservation(provider=provider_id, requested_model=model_name)
        state.observations.append(observation)
        started = self._clock()
        try:
            if provider is None or model is None:
                raise DispatchAborted(AttemptFailed(FailureKind.INTERNAL_ERROR, provider_id, model_name, "SDK selected an unapproved route", provider_fault=False))
            approval = get_dispatch_approval()
            if approval is not None and provider_id not in approval.provider_ids:
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, provider_id, model_name, "processing destination is not approved by server policy", provider_fault=False)
            if state.request.json_mode and (provider_id, model_name) not in self._json_models:
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, provider_id, model_name, "JSON capability lacks explicit verified metadata", provider_fault=False)
            if model.context is None or estimate_request_tokens(state.request) > model.context:
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.CONTEXT_WINDOW_EXCEEDED, provider_id, model_name, "context window exceeded or unknown")
            remaining_cooldown = self.cooling_remaining(provider_id, model_name)
            if remaining_cooldown > 0:
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.RATE_LIMITED, provider_id, model_name, "provider is cooling", retry_after_s=remaining_cooldown)
            if self._quota_remaining is not None and self._quota_remaining(provider_id) <= 0:
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.QUOTA_EXHAUSTED, provider_id, model_name, "account allowance is exhausted")
            if self.pool is not None and not await asyncio.to_thread(self.pool.quota.reserve, provider_id, model_name, model.rpd):
                observation.outcome, observation.consumption = "skipped", "none"
                raise AttemptFailed(FailureKind.QUOTA_EXHAUSTED, provider_id, model_name, "published daily model allowance is exhausted")
            payload = dict(body)
            output_tokens = state.request.max_output_tokens if state.request.max_output_tokens is not None else DEFAULT_EXPECTED_OUTPUT_TOKENS
            if provider.adapter == "gemini":
                settings = dict(payload.get("generationConfig") or {})
                settings["maxOutputTokens"] = output_tokens
                if state.request.json_mode:
                    settings["responseMimeType"] = "application/json"
                payload["generationConfig"] = settings
            else:
                payload["max_tokens"] = output_tokens
                if state.request.json_mode:
                    payload["response_format"] = {"type": "json_object"}
            remaining = min(timeout, state.deadline - asyncio.get_running_loop().time())
            if self._reserve_attempt is not None:
                reservation = self._reserve_attempt(provider_id)
                if reservation is None:
                    observation.outcome, observation.consumption = "skipped", "none"
                    raise AttemptFailed(FailureKind.QUOTA_EXHAUSTED, provider_id, model_name, "account allowance is reserved or exhausted", provider_fault=False)
                observation.account_reservation_id = reservation
            result = await await_before(self._post(url, headers, payload, remaining), state.deadline)
            if not isinstance(result, HTTPResult):
                raise TypeError("transport must return HTTPResult")
            observation.status_code = result.status
            observation.retry_after_s = retry_after_hint(result.headers, result.body if isinstance(result.body, dict) else result.text)
            if result.status != 200:
                raise AttemptFailed(_map_http_status(result.status, json.dumps(result.body)), provider_id, model_name, "provider HTTP failure", retry_after_s=observation.retry_after_s)
            observation.consumption = "known"
            if not isinstance(result.body, dict):
                raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "provider response must be an object")
            reported = result.body.get("model") or result.body.get("modelVersion")
            observation.reported_model = reported if isinstance(reported, str) and reported.strip() else None
            if provider.adapter == "gemini":
                candidates = result.body.get("candidates")
                if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
                    raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "invalid Gemini envelope")
                chosen = candidates[0]
                content = chosen.get("content") or {}
                parts = content.get("parts") if isinstance(content, dict) else None
                if not isinstance(parts, list) or not all(isinstance(part, dict) and isinstance(part.get("text", ""), str) for part in parts):
                    raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "invalid Gemini text parts")
                text = "".join(part.get("text", "") for part in parts)
                raw_usage = result.body.get("usageMetadata") or {}
                usage_data = {"prompt_tokens": raw_usage.get("promptTokenCount"), "completion_tokens": raw_usage.get("candidatesTokenCount")} if isinstance(raw_usage, dict) else None
                observation.finish_reason = chosen.get("finishReason")
            else:
                choices = result.body.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) or not isinstance(choices[0].get("message"), dict):
                    raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "invalid completion envelope")
                text = choices[0]["message"].get("content")
                usage_data = result.body.get("usage") or {}
                observation.finish_reason = choices[0].get("finish_reason")
            if not isinstance(usage_data, dict):
                raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "invalid token usage envelope")
            usage = validated_usage(usage_data, provider_id, model_name)
            observation.input_tokens, observation.output_tokens = usage.input_tokens, usage.output_tokens
            validate_text(text, state.request, provider_id, model_name, finish_reason=observation.finish_reason)
            if usage.output_tokens is not None and usage.output_tokens > output_tokens:
                raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, provider_id, model_name, "output exceeded requested token limit")
            observation.outcome = "succeeded"
            observation.latency_ms = (self._clock() - started) * 1000
            return result
        except asyncio.CancelledError as exc:
            observation.outcome = "aborted"
            setattr(exc, "observations", list(state.observations))
            raise
        except DeadlineExpired as exc:
            observation.outcome = "aborted"
            raise DispatchAborted(AttemptFailed(FailureKind.TIMEOUT, provider_id, model_name, "attempt budget exceeded; consumption unknown", observations=state.observations, provider_fault=False)) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            observation.failure_kind = FailureKind.TIMEOUT if isinstance(exc, httpx.TimeoutException) else FailureKind.CONNECTION
            observation.outcome = "failed"
            observation.latency_ms = (self._clock() - started) * 1000
            self._cool(observation)
            raise ProviderHTTPError(408 if observation.failure_kind == FailureKind.TIMEOUT else 502, observation.failure_kind.value, retryable=True) from exc
        except AttemptFailed as exc:
            observation.failure_kind = exc.kind
            observation.retry_after_s = exc.retry_after_s or observation.retry_after_s
            if observation.outcome != "skipped":
                observation.outcome = "failed"
                observation.latency_ms = (self._clock() - started) * 1000
                self._cool(observation)
            status = observation.status_code if observation.status_code and observation.status_code != 200 else 502
            detail = "context window exceeded" if exc.kind == FailureKind.CONTEXT_WINDOW_EXCEEDED else exc.kind.value
            raise ProviderHTTPError(status, detail, retryable=True) from exc
        except Exception as exc:
            observation.outcome = "unknown"
            raise DispatchAborted(AttemptFailed(FailureKind.INTERNAL_ERROR, provider_id, model_name, f"transport programming error: {type(exc).__name__}", observations=state.observations, provider_fault=False)) from exc