"""OpenRouterAdapter — direct OpenRouter provider adapter (RULES.md R1).

Routes to whatever free chat models OpenRouter currently lists: the catalogue
is discovered live (public /models endpoint) because a hard-coded list of
``:free`` ids drifts to 404s within weeks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from decimal import Decimal, InvalidOperation
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Optional
import httpx

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate, StreamDelta, StreamDone, StreamEvent
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import get_dispatch_approval
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.latency import DeadlineContext, DeadlineExpired, await_before, remaining_attempt_timeout_s
from bebshax.llm.retry import retry_after_hint
from bebshax.llm.provenance import ProviderObservation
from bebshax.llm.types import LLMRequest, TokenUsage
from bebshax.llm.validation import validate_text, validated_usage

if TYPE_CHECKING:
    from bebshax.llm.service import LLMService

logger = logging.getLogger(__name__)

PROVIDER = "openrouter"
# Policy sentinel: any upstream OpenRouter routes to under data_collection=deny,
# instead of an explicit host allowlist (`provider.only`).
ANY_DATA_DENYING_UPSTREAM = "*"
# Seed list ONLY — used when the live catalogue cannot be fetched (offline) and
# no BEBSHAX_OPENROUTER_MODELS pin is set. OpenRouter's free catalogue drifts
# (the previous three seeds all 404'd within weeks), so production discovers
# the current ``:free`` models from the public catalogue instead; see
# ``discover_free_models``. Reasoning-heavy routes are avoided on purpose: they
# burned 100 s+ per interactive turn. ``openrouter/auto`` is deliberately absent:
# it routes to PAID models, which breaks the $0 thesis.
DEFAULT_MODELS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-26b-a4b-it:free",
]
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"
CATALOGUE_TTL_S = 30 * 60
CATALOGUE_MAX_MODELS = None
# Free routes that are the wrong tool for persona work: safety classifiers,
# code-only models and chain-of-thought "reasoning" variants (slow, verbose).
_CATALOGUE_EXCLUDE_RE = re.compile(r"safety|guard|code|reasoning|thinking|-r1", re.IGNORECASE)
RESPONSE_FORMAT_DROPPED_NOTE = "response_format dropped after 400"

# OpenRouter reports prompt overflow as 400 (sometimes 413) with a prose body,
# e.g. "This endpoint's maximum context length is 8192 tokens".
_CONTEXT_OVERFLOW_BODY_RE = re.compile(
    r"context|maximum.*tokens|too long|token limit", re.IGNORECASE | re.DOTALL
)
# A 429 whose body names the UPSTREAM shared pool of one model ("<model> is
# temporarily rate-limited upstream", limit_source=upstream_provider_shared_pool)
# is that model's problem, not our account's: benching every OpenRouter route
# for it (provider-wide RATE_LIMITED) blacked out three healthy models live.
_UPSTREAM_MODEL_LIMIT_RE = re.compile(
    r"upstream_provider_shared_pool|rate-limited upstream", re.IGNORECASE
)
# The account's free-tier DAY cap ("Rate limit exceeded: free-models-per-day",
# limit_source=openrouter_free_tier_daily, X-RateLimit-Reset in the body). A
# quota, not a burst: nothing will succeed until the reset, so the route is
# cooled until then instead of being re-probed every minute.
_DAILY_QUOTA_RE = re.compile(r"free-models-per-day|openrouter_free_tier_daily|per-day", re.IGNORECASE)
_RESET_MS_RE = re.compile(r'X-RateLimit-Reset\\?"?\s*:\s*\\?"?(\d{10,16})')


def _configured_models() -> list[str]:
    """Model list — BEBSHAX_OPENROUTER_MODELS (comma-separated) overrides the
    defaults above. Free-tier catalogs drift; operators repoint without a
    release. Adapter-local env read, same pattern as OLLAMA_API_BASE (R1)."""
    raw = os.environ.get("BEBSHAX_OPENROUTER_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or list(DEFAULT_MODELS)


def _pinned_models() -> list[str]:
    raw = os.environ.get("BEBSHAX_OPENROUTER_MODELS", "")
    return [m.strip() for m in raw.split(",") if m.strip()]


def rank_free_catalogue(
    catalogue: list[dict], *, limit: int | None = None, request: LLMRequest | None = None
) -> list[dict]:
    """Retain all verified free text models; order only after request context is known."""
    rows: list[tuple[int, int, str, dict]] = []
    seen: set[str] = set()
    for row in catalogue:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        if not isinstance(model_id, str) or not model_id.endswith(":free") or model_id in seen:
            continue
        if _CATALOGUE_EXCLUDE_RE.search(model_id):
            continue
        try:
            context = row.get("context_length")
            if type(context) is not int or context <= 0:
                continue
            pricing = row.get("pricing")
            if not isinstance(pricing, dict):
                continue
            prices = [Decimal(str(pricing.get(key))) for key in ("prompt", "completion")]
            if any(not price.is_finite() or price != 0 for price in prices):
                continue
        except (InvalidOperation, TypeError, ValueError):
            continue
        parameters = row.get("supported_parameters")
        if not isinstance(parameters, list) or not all(isinstance(value, str) for value in parameters):
            continue
        architecture = row.get("architecture") or {}
        if not isinstance(architecture, dict) or "text" not in architecture.get("output_modalities", ["text"]):
            continue
        seen.add(model_id)
        structured = request is None or request.json_mode
        priority = 0 if not structured or "response_format" in parameters else 1
        rows.append((priority, -context, model_id, row))
    rows.sort(key=lambda item: item[:3])
    return [row for _, _, _, row in rows[:limit]]


def _is_context_overflow_body(body: str | None) -> bool:
    return bool(body) and _CONTEXT_OVERFLOW_BODY_RE.search(body) is not None


def _map_http_status(status: int | None, body: str | None = None) -> FailureKind:
    if status == 429:
        if body and _UPSTREAM_MODEL_LIMIT_RE.search(body):
            return FailureKind.MODEL_UNAVAILABLE  # route-scoped cooldown; siblings stay usable
        if body and _DAILY_QUOTA_RE.search(body):
            return FailureKind.QUOTA_EXHAUSTED  # the day's allowance is gone — account-level
        return FailureKind.RATE_LIMITED  # our account/key: provider-scoped
    if status == 402:
        return FailureKind.QUOTA_EXHAUSTED  # credits/free allowance gone — account-level
    if status == 408:
        return FailureKind.TIMEOUT
    if status in (401, 403):
        return FailureKind.AUTH_INVALID
    if status == 404:
        return FailureKind.MODEL_UNAVAILABLE
    if status in (400, 413) and _is_context_overflow_body(body):
        return FailureKind.CONTEXT_WINDOW_EXCEEDED  # advance to a roomier route, no cooldown
    if status == 413:
        return FailureKind.CONTEXT_WINDOW_EXCEEDED
    if status in (400, 422):
        return FailureKind.CAPABILITY_UNSUPPORTED
    if status is not None and status >= 500:
        return FailureKind.SERVER_ERROR
    return FailureKind.PROVIDER_UNAVAILABLE


def _retry_after_hint(headers, body: str | None, *, now: float | None = None) -> float | None:
    return retry_after_hint(headers, body, now=now)


class OpenRouterAdapter(ProviderAdapter):
    """Adapter for OpenRouter chat completions."""

    streaming_mode = "native"
    remote_processing = True

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = DEFAULT_MODELS[0],
        timeout: float = 30.0,
        *,
        discover_catalogue: bool = False,
        catalogue_ttl_s: float = CATALOGUE_TTL_S,
        catalogue: list[dict] | None = None,
        client: httpx.AsyncClient | None = None,
        reserve_attempt: Callable[[str], str | None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout
        self._reserve_attempt = reserve_attempt
        self._client: Optional[httpx.AsyncClient] = client
        # Live catalogue discovery is opt-in (production wiring turns it on) so
        # unit tests and offline tools never touch the network by accident.
        self._discover = discover_catalogue
        self._catalogue_ttl = catalogue_ttl_s
        self._catalogue: list[RouteCandidate] | None = None
        self._catalogue_fetched_at: float = 0.0
        self._catalogue_error: str | None = None
        self._catalogue_lock = asyncio.Lock()
        self._catalogue_rows: list[dict] = []
        self._last_failed_fetch: float | None = None
        # Models whose catalogue entry exposes the `reasoning` toggle. Free
        # reasoning models spend the whole output budget thinking and return
        # an EMPTY message (observed live: 254 reasoning tokens, content ""),
        # so those routes are asked for a plain answer explicitly.
        self._reasoning_toggle_models: set[str] = set()
        if catalogue is not None:
            self._set_catalogue(catalogue)

    def _set_catalogue(self, rows: list[dict]) -> None:
        self._catalogue_rows = rank_free_catalogue(rows)
        self._catalogue = []
        for row in self._catalogue_rows:
            top = row.get("top_provider") or {}
            top = top if isinstance(top, dict) else {}
            context = row["context_length"]
            top_context = top.get("context_length")
            if type(top_context) is int and top_context > 0:
                context = min(context, top_context)
            output_cap = top.get("max_completion_tokens")
            self._catalogue.append(RouteCandidate(
                provider=PROVIDER, model=row["id"], context_window=context,
                supports_json="response_format" in row["supported_parameters"],
                supports_tools=False,
                supported_parameters=list(row["supported_parameters"]),
                max_output_tokens=output_cap if type(output_cap) is int and output_cap > 0 else None,
            ))
        self._catalogue_fetched_at = time.monotonic()
        self._catalogue_error = None
        self._last_failed_fetch = None

    def _get_api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key
        return os.environ.get("OPENROUTER_API_KEY")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout, trust_env=False, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def configured_models(self) -> list[str]:
        """Models this adapter would offer without discovery (env pin or seed) — no network."""
        return _configured_models()

    def catalogue_status(self) -> dict:
        """What the live catalogue produced (for health/observability): the
        discovered routes, when they were fetched, and the last fetch error."""
        return {
            "discovery_enabled": self._discover,
            "pinned": _pinned_models(),
            "discovered": [c.model for c in (self._catalogue or [])],
            "fetched_at": self._catalogue_fetched_at or None,
            "error": self._catalogue_error,
        }

    async def discover_free_models(self) -> list[RouteCandidate]:
        """Fetch OpenRouter's public catalogue (no key needed) and turn the
        currently listed free chat models into route candidates. Cached for
        ``catalogue_ttl_s``; a failed refresh keeps the previous catalogue and
        records the error instead of raising."""
        async with self._catalogue_lock:
            fresh = self._catalogue is not None and (
                time.monotonic() - self._catalogue_fetched_at
            ) < self._catalogue_ttl
            if fresh:
                return list(self._catalogue or [])
            if self._last_failed_fetch is not None and time.monotonic() - self._last_failed_fetch < 5:
                return []
            try:
                client = await self._get_client()
                resp = await client.get(OPENROUTER_MODELS_ENDPOINT)
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    raise ValueError("catalogue must contain a data array")
                self._set_catalogue(payload["data"])
                logger.info(
                    "openrouter catalogue: %d free route(s) discovered: %s",
                    len(self._catalogue or []),
                    ", ".join(candidate.model for candidate in self._catalogue or []),
                )
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                self._catalogue_error = type(exc).__name__
                self._last_failed_fetch = time.monotonic()
                logger.warning("openrouter catalogue discovery failed: %s", self._catalogue_error)
                return []
            return list(self._catalogue or [])

    def configuration_status(self, model: Optional[str] = None) -> dict:
        """Configuration report with NO network call and no LLM spend: is a key
        present, which models are configured. Verification of the key is the
        job of health_check() (authenticated, rate-limited POST /test)."""
        key = self._get_api_key()
        configured = bool(key and key.strip())
        target_model = model or os.environ.get("OPENROUTER_MODEL") or self._default_model
        if not configured:
            return {
                "configured": False,
                "authenticated": False,
                "model": target_model,
                "models": [],
                "status": "not_configured",
                "error_code": "OPENROUTER_NOT_CONFIGURED",
                "message": "OPENROUTER_API_KEY is not set in environment or .env.",
            }
        return {
            "configured": True,
            "authenticated": False,  # not verified here — POST /test performs the live probe
            "model": target_model,
            "models": self.configured_models(),
            "status": "configured",
            "message": (
                "OPENROUTER_API_KEY is configured (not verified). "
                "POST /api/health/openrouter/test runs an authenticated live probe."
            ),
        }

    async def candidates(self) -> list[RouteCandidate]:
        approval = get_dispatch_approval()
        if approval is not None and not approval.openrouter_upstreams:
            return []
        key = self._get_api_key()
        if not key or not key.strip():
            return []  # No key configured; cleanly skip to next adapter in pool

        if self._discover:
            discovered = await self.discover_free_models()
        elif self._catalogue is not None and time.monotonic() - self._catalogue_fetched_at < self._catalogue_ttl:
            discovered = list(self._catalogue)
        else:
            discovered = []
        pinned = _pinned_models()
        if pinned:
            return [candidate for model in pinned for candidate in discovered if candidate.model == model]
        return discovered

    async def candidates_for(self, request: LLMRequest) -> list[RouteCandidate]:
        candidates = await self.candidates()
        if not request.json_mode and not _pinned_models():
            candidates.sort(key=lambda candidate: -candidate.context_window)
        return candidates

    async def _validate_candidate(self, candidate: RouteCandidate, request: LLMRequest) -> RouteCandidate:
        if request.tools_required:
            raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, candidate.model, "tool execution contract is unavailable")
        verified = next((route for route in await self.candidates() if route.model == candidate.model), None)
        if candidate.provider != PROVIDER or verified is None:
            raise AttemptFailed(FailureKind.MODEL_UNAVAILABLE, PROVIDER, candidate.model, "model lacks current verified free catalogue metadata")
        if estimate_request_tokens(request) > verified.context_window:
            raise AttemptFailed(FailureKind.CONTEXT_WINDOW_EXCEEDED, PROVIDER, candidate.model, "full request exceeds verified context")
        parameters = verified.supported_parameters or []
        required = {"response_format"} if request.json_mode else set()
        if request.max_output_tokens is not None:
            required.add("max_tokens")
        if request.temperature is not None:
            required.add("temperature")
        if not required.issubset(parameters):
            raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, candidate.model, "requested parameters are unsupported")
        if verified.max_output_tokens is not None and request.max_output_tokens is not None and request.max_output_tokens > verified.max_output_tokens:
            raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, candidate.model, "requested output budget exceeds verified model limit")
        return verified

    def _provider_preferences(self) -> dict:
        preferences = {"data_collection": "deny", "require_parameters": True}
        approval = get_dispatch_approval()
        if approval is not None:
            preferences["max_price"] = {"prompt": 0, "completion": 0}
            if ANY_DATA_DENYING_UPSTREAM not in approval.openrouter_upstreams:
                preferences.update({"only": list(approval.openrouter_upstreams), "allow_fallbacks": False})
        return preferences

    def _reserve_observation(self, observation: ProviderObservation) -> None:
        if self._reserve_attempt is None:
            return
        reservation = self._reserve_attempt(PROVIDER)
        if reservation is None:
            observation.outcome, observation.consumption = "skipped", "none"
            raise AttemptFailed(
                FailureKind.QUOTA_EXHAUSTED, PROVIDER, observation.requested_model,
                "account allowance is reserved or exhausted", provider_fault=False, observations=[observation],
            )
        observation.account_reservation_id = reservation

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        candidate = await self._validate_candidate(candidate, request)
        key = self._get_api_key()
        if not key:
            raise AttemptFailed(
                FailureKind.AUTH_INVALID,
                PROVIDER,
                candidate.model,
                "OPENROUTER_API_KEY is not set",
            )

        client = await self._get_client()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload: dict = {
            "model": candidate.model,
            "messages": messages,
            "provider": self._provider_preferences(),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "HTTP-Referer": "https://bebshax.ai",
            "X-Title": "BebshaX AI Persona Validation",
            "Content-Type": "application/json",
        }

        # Per-attempt budget by task class overrides the client-wide default.
        budget = remaining_attempt_timeout_s(request.task)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        req_timeout = httpx.Timeout(budget, connect=min(10.0, budget))
        started = time.perf_counter()
        observation = ProviderObservation(provider=PROVIDER, requested_model=candidate.model)
        self._reserve_observation(observation)
        try:
            resp = await await_before(client.post(
                OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=req_timeout
            ), deadline)
        except asyncio.CancelledError as exc:
            observation.outcome = "aborted"
            setattr(exc, "observations", [observation])
            raise
        except TimeoutError as exc:
            observation.outcome = "aborted"
            raise AttemptFailed(
                FailureKind.TIMEOUT, PROVIDER, candidate.model, "attempt budget exceeded", observations=[observation], provider_fault=False
            ) from exc
        except httpx.TimeoutException as exc:
            observation.outcome, observation.failure_kind = "failed", FailureKind.TIMEOUT
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, "transport timed out", observations=[observation]) from exc
        except httpx.TransportError as exc:
            observation.outcome, observation.failure_kind = "failed", FailureKind.CONNECTION
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, "transport connection failed", observations=[observation]) from exc

        if resp.status_code != 200:
            kind = _map_http_status(resp.status_code, resp.text)
            observation.status_code = resp.status_code
            observation.outcome = "failed"
            observation.failure_kind = kind
            observation.retry_after_s = _retry_after_hint(resp.headers, resp.text)
            observation.latency_ms = (time.perf_counter() - started) * 1000
            raise AttemptFailed(
                kind,
                PROVIDER,
                candidate.model,
                f"OpenRouter HTTP {resp.status_code}",
                retry_after_s=observation.retry_after_s,
                observations=[observation],
            )

        try:
            data = resp.json()
        except ValueError as exc:
            observation.status_code = 200
            observation.outcome, observation.consumption = "failed", "known"
            observation.failure_kind = FailureKind.MALFORMED_RESPONSE
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "Failed to parse JSON response",
                observations=[observation],
            ) from exc

        return self._observed_completion(data, candidate, request, started, observation.account_reservation_id)

    def _observed_completion(
        self, data, candidate: RouteCandidate, request: LLMRequest, started: float, account_reservation_id: str | None = None,
    ) -> AdapterCompletion:
        observation = ProviderObservation(provider=PROVIDER, requested_model=candidate.model, status_code=200, consumption="known", account_reservation_id=account_reservation_id)
        if isinstance(data, dict):
            reported = data.get("model")
            observation.reported_model = reported if isinstance(reported, str) else None
            usage = data.get("usage")
            if isinstance(usage, dict):
                observation.input_tokens = usage.get("prompt_tokens") if type(usage.get("prompt_tokens")) is int else None
                observation.output_tokens = usage.get("completion_tokens") if type(usage.get("completion_tokens")) is int else None
        observation.latency_ms = (time.perf_counter() - started) * 1000
        try:
            completion = self._completion_from_data(data, candidate, request)
        except AttemptFailed as exc:
            observation.outcome = "failed"
            observation.failure_kind = exc.kind
            exc.observations = [observation]
            raise
        observation.outcome = "succeeded"
        observation.finish_reason = completion.finish_reason
        completion.observations = [observation]
        completion.latency_ms = observation.latency_ms
        return completion

    def _completion_from_data(self, data, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        if not isinstance(data, dict):
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "OpenRouter response must be a JSON object",
            )
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "No valid choices returned in OpenRouter response",
            )

        if not isinstance(choices[0], dict) or not isinstance(choices[0].get("message"), dict):
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "OpenRouter choice must contain a message object",
            )
        usage_data = data.get("usage", {})
        if not isinstance(usage_data, dict):
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "OpenRouter usage must be an object",
            )
        msg = choices[0]["message"]
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            reasoning_details = usage_data.get("completion_tokens_details")
            reasoning_tokens = (
                reasoning_details.get("reasoning_tokens") or 0
                if isinstance(reasoning_details, dict) else 0
            )
            detail = "Empty text in OpenRouter message choice"
            if reasoning_tokens:
                detail = (
                    f"reply had no content: the model spent {reasoning_tokens} reasoning tokens "
                    f"(finish_reason={choices[0].get('finish_reason')}) and never answered"
                )
            raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, detail)

        # Mechanical truncation signal: the model ran out of output budget
        # (reasoning models burning the cap on chain-of-thought leak raw,
        # unusable analysis text). Policy: retry once, then next candidate.
        if choices[0].get("finish_reason") == "length":
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "Output truncated at max_tokens (finish_reason=length)",
            )

        usage = validated_usage(usage_data, PROVIDER, candidate.model)
        validate_text(content, request, PROVIDER, candidate.model, finish_reason=choices[0].get("finish_reason"))
        if request.max_output_tokens is not None and usage.output_tokens is not None and usage.output_tokens > request.max_output_tokens:
            raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "output exceeded requested token limit")
        reported = data.get("model")
        serving_model = reported if isinstance(reported, str) and reported.strip() else "unknown"
        notes = [
            f"requested OpenRouter route: {candidate.model}",
            f"reported serving model: {serving_model}",
            f"finish_reason: {choices[0].get('finish_reason') or 'unknown'}",
        ]

        return AdapterCompletion(
            text=content,
            usage=usage,
            provider=PROVIDER,
            model=serving_model,
            notes=notes,
            finish_reason=choices[0].get("finish_reason"),
        )

    async def stream(self, candidate: RouteCandidate, request: LLMRequest) -> AsyncGenerator[StreamEvent, None]:
        budget = remaining_attempt_timeout_s(request.task)
        deadline = asyncio.get_running_loop().time() + budget
        started = time.perf_counter()
        candidate = await await_before(self._validate_candidate(candidate, request), deadline)
        key = self._get_api_key()
        if not key:
            raise AttemptFailed(FailureKind.AUTH_INVALID, PROVIDER, candidate.model, "OPENROUTER_API_KEY is not set")
        payload = {
            "model": candidate.model,
            "messages": [{"role": message.role, "content": message.content} for message in request.messages],
            "provider": self._provider_preferences(),
            "stream": True, "stream_options": {"include_usage": True},
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key.strip()}", "Content-Type": "application/json", "X-Title": "BebshaX"}
        client = await self._get_client()
        fragments: list[str] = []
        leading = ""
        visible = False
        usage: dict = {}
        reported_model = None
        finish_reason = None
        terminal = False
        observation = ProviderObservation(provider=PROVIDER, requested_model=candidate.model)
        self._reserve_observation(observation)
        try:
            async with DeadlineContext(client.stream("POST", OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=httpx.Timeout(budget, connect=min(10.0, budget))), deadline) as response:
                observation.status_code = response.status_code
                if response.status_code != 200:
                    await await_before(response.aread(), deadline)
                    raise AttemptFailed(
                        _map_http_status(response.status_code, response.text), PROVIDER, candidate.model,
                        f"OpenRouter HTTP {response.status_code}", retry_after_s=_retry_after_hint(response.headers, response.text),
                    )
                lines = response.aiter_lines()
                event_lines: list[str] = []
                received = 0
                while True:
                    try:
                        line = await await_before(anext(lines), deadline)
                    except StopAsyncIteration:
                        break
                    received += len(line)
                    if received > 32 * 1024 * 1024:
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "stream exceeds response byte limit")
                    if line.startswith("data:"):
                        event_lines.append(line[5:].lstrip())
                        continue
                    if line or not event_lines:
                        continue
                    data = "\n".join(event_lines)
                    event_lines = []
                    if data == "[DONE]":
                        terminal = True
                        break
                    try:
                        event = json.loads(data)
                    except ValueError as exc:
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "invalid stream event JSON") from exc
                    if not isinstance(event, dict):
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "stream event must be an object")
                    if isinstance(event.get("error"), dict):
                        code = event["error"].get("code")
                        kind = _map_http_status(code, json.dumps(event)) if type(code) is int else FailureKind.SERVER_ERROR
                        raise AttemptFailed(kind, PROVIDER, candidate.model, "provider stream error", retry_after_s=_retry_after_hint(response.headers, json.dumps(event)))
                    model = event.get("model")
                    if model is not None:
                        if not isinstance(model, str) or (reported_model is not None and model != reported_model):
                            raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "serving model changed within stream")
                        reported_model = model
                    if "usage" in event and event["usage"] is not None:
                        if not isinstance(event["usage"], dict):
                            raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "invalid stream usage")
                        usage = event["usage"]
                    choices = event.get("choices", [])
                    if not isinstance(choices, list) or len(choices) > 1:
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "invalid stream choices")
                    if not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict) or not isinstance(choice.get("delta", {}), dict):
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "invalid stream delta")
                    delta = choice.get("delta", {})
                    text = delta.get("content")
                    if text is None:
                        text = ""
                    if not isinstance(text, str):
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "non-text stream delta")
                    if delta.get("tool_calls"):
                        raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, candidate.model, "tool execution contract is unavailable")
                    if finish_reason is not None and text:
                        raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "text arrived after finish reason")
                    if choice.get("finish_reason") is not None:
                        finish_reason = choice["finish_reason"]
                    fragments.append(text)
                    if not request.json_mode:
                        leading += text
                        if visible or leading.strip():
                            visible = True
                            if leading:
                                yield StreamDelta(text=leading)
                            leading = ""
            if not terminal or finish_reason is None:
                raise AttemptFailed(FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "stream ended without a terminal completion")
            completion = self._observed_completion({
                "model": reported_model, "usage": usage,
                "choices": [{"message": {"content": "".join(fragments)}, "finish_reason": finish_reason}],
            }, candidate, request, started, observation.account_reservation_id)
            if request.json_mode:
                yield StreamDelta(text=completion.text)
            yield StreamDone(completion=completion)
        except (asyncio.CancelledError, GeneratorExit) as exc:
            observation.outcome = "aborted"
            observation.reported_model = reported_model
            setattr(exc, "observations", [observation])
            raise
        except (DeadlineExpired, httpx.TimeoutException) as exc:
            observation.outcome = "aborted"
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, "stream budget exceeded", observations=[observation], provider_fault=False) from exc
        except httpx.TransportError as exc:
            observation.outcome = "failed"
            observation.failure_kind = FailureKind.CONNECTION
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, "stream transport failed", observations=[observation]) from exc
        except AttemptFailed as exc:
            observation.outcome = "failed"
            observation.failure_kind = exc.kind
            observation.retry_after_s = exc.retry_after_s
            observation.reported_model = reported_model
            if not exc.observations:
                exc.observations = [observation]
            raise

    async def health_check(self, model: Optional[str] = None, *, llm_service: LLMService) -> dict:
        from bebshax.llm.openrouter_service import OpenRouterService

        return await OpenRouterService(self).health_check(model=model, llm_service=llm_service)

