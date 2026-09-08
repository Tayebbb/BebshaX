"""OpenRouterAdapter — direct OpenRouter provider adapter (RULES.md R1).

Routes to whatever free chat models OpenRouter currently lists: the catalogue
is discovered live (public /models endpoint) because a hard-coded list of
``:free`` ids drifts to 404s within weeks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Optional
import httpx

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.latency import attempt_timeout_s
from bebshax.llm.types import LLMRequest, TokenUsage

logger = logging.getLogger(__name__)

PROVIDER = "openrouter"
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
CATALOGUE_MAX_MODELS = 4
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


def rank_free_catalogue(catalogue: list[dict], *, limit: int = CATALOGUE_MAX_MODELS) -> list[dict]:
    """Pick the free chat models worth routing to, from a /models payload.

    Pure function over the catalogue rows (``id``, ``context_length``,
    ``supported_parameters``): keeps ``:free`` ids, drops the excluded
    families, prefers routes that accept ``response_format`` (structured
    output is most of this product's traffic) and then larger context windows.
    """
    rows: list[tuple[int, int, str, dict]] = []
    for row in catalogue:
        model_id = str(row.get("id") or "")
        if not model_id.endswith(":free") or _CATALOGUE_EXCLUDE_RE.search(model_id):
            continue
        params = set(row.get("supported_parameters") or [])
        context = int(row.get("context_length") or 0)
        rows.append((0 if "response_format" in params else 1, -context, model_id, row))
    rows.sort()
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
    if status is not None and status >= 500:
        return FailureKind.SERVER_ERROR
    return FailureKind.PROVIDER_UNAVAILABLE


def _retry_after_hint(headers, body: str | None, *, now: float | None = None) -> float | None:
    """Seconds until the provider says it will serve again, from a Retry-After
    header or the ``X-RateLimit-Reset`` epoch-ms OpenRouter embeds in quota
    errors. None when the provider gave no usable hint."""
    raw = None
    try:
        raw = headers.get("Retry-After") if headers is not None else None
    except Exception:  # noqa: BLE001 — header containers vary between transports
        raw = None
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    match = _RESET_MS_RE.search(body or "")
    if match:
        reset_ms = int(match.group(1))
        current = time.time() if now is None else now
        reset_s = reset_ms / 1000.0 if reset_ms > 10**11 else float(reset_ms)
        remaining = reset_s - current
        return max(0.0, remaining) if remaining > 0 else None
    return None


class OpenRouterAdapter(ProviderAdapter):
    """Adapter for OpenRouter chat completions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = DEFAULT_MODELS[0],
        timeout: float = 30.0,
        *,
        discover_catalogue: bool = False,
        catalogue_ttl_s: float = CATALOGUE_TTL_S,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        # Live catalogue discovery is opt-in (production wiring turns it on) so
        # unit tests and offline tools never touch the network by accident.
        self._discover = discover_catalogue
        self._catalogue_ttl = catalogue_ttl_s
        self._catalogue: list[RouteCandidate] | None = None
        self._catalogue_fetched_at: float = 0.0
        self._catalogue_error: str | None = None
        self._catalogue_lock = asyncio.Lock()
        # Models whose catalogue entry exposes the `reasoning` toggle. Free
        # reasoning models spend the whole output budget thinking and return
        # an EMPTY message (observed live: 254 reasoning tokens, content ""),
        # so those routes are asked for a plain answer explicitly.
        self._reasoning_toggle_models: set[str] = set()

    def _get_api_key(self) -> str | None:
        if self._api_key is not None:
            return self._api_key
        return os.environ.get("OPENROUTER_API_KEY")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
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
            try:
                client = await self._get_client()
                resp = await client.get(OPENROUTER_MODELS_ENDPOINT)
                resp.raise_for_status()
                rows = resp.json().get("data") or []
                ranked = rank_free_catalogue(rows)
                self._catalogue = [
                    RouteCandidate(
                        provider=PROVIDER,
                        model=str(row["id"]),
                        context_window=int(row.get("context_length") or 128_000),
                        supports_json="response_format" in set(row.get("supported_parameters") or []),
                        supports_tools="tools" in set(row.get("supported_parameters") or []),
                    )
                    for row in ranked
                ]
                self._reasoning_toggle_models = {
                    str(row["id"]) for row in ranked if "reasoning" in set(row.get("supported_parameters") or [])
                }
                self._catalogue_fetched_at = time.monotonic()
                self._catalogue_error = None
                logger.info(
                    "openrouter catalogue: %d free route(s) discovered: %s",
                    len(self._catalogue),
                    ", ".join(c.model for c in self._catalogue),
                )
            except Exception as exc:  # noqa: BLE001 — discovery must degrade, never crash routing
                self._catalogue_error = f"{type(exc).__name__}: {exc}"[:200]
                self._catalogue_fetched_at = time.monotonic()  # do not hammer a failing endpoint
                if self._catalogue is None:
                    self._catalogue = []
                logger.warning("openrouter catalogue discovery failed: %s", self._catalogue_error)
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
        key = self._get_api_key()
        if not key or not key.strip():
            return []  # No key configured; cleanly skip to next adapter in pool

        def _static(models: list[str]) -> list[RouteCandidate]:
            return [
                RouteCandidate(
                    provider=PROVIDER,
                    model=m,
                    context_window=128_000,
                    supports_json=True,
                    supports_tools=False,
                )
                for m in models
            ]

        pinned = _pinned_models()
        if pinned:
            return _static(pinned)  # operator pin always wins
        if self._discover:
            discovered = await self.discover_free_models()
            if discovered:
                return discovered
        return _static(list(DEFAULT_MODELS))

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
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
            "temperature": request.temperature if request.temperature is not None else 0.7,
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if candidate.model in self._reasoning_toggle_models:
            # Persona/structured work wants the answer, not the chain of thought;
            # verified live: with the toggle off the same model returns content
            # with 0 reasoning tokens instead of an empty, budget-exhausted reply.
            payload["reasoning"] = {"enabled": False}

        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "HTTP-Referer": "https://bebshax.ai",
            "X-Title": "BebshaX AI Persona Validation",
            "Content-Type": "application/json",
        }

        # Per-attempt budget by task class overrides the client-wide default.
        req_timeout = httpx.Timeout(attempt_timeout_s(request.task), connect=10.0)
        degradation_notes: list[str] = []
        try:
            resp = await client.post(
                OPENROUTER_ENDPOINT, json=payload, headers=headers, timeout=req_timeout
            )
            if (
                resp.status_code == 400
                and "response_format" in payload
                and not _is_context_overflow_body(resp.text)
            ):
                # Some models reject response_format; retry without it (the prompt
                # already demands JSON). A context-overflow 400 is NOT retried — the
                # same prompt would overflow again. Provenance records the drop.
                retry_payload = {k: v for k, v in payload.items() if k != "response_format"}
                resp = await client.post(
                    OPENROUTER_ENDPOINT, json=retry_payload, headers=headers, timeout=req_timeout
                )
                degradation_notes.append(RESPONSE_FORMAT_DROPPED_NOTE)
        except httpx.TimeoutException as exc:
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, str(exc)) from exc
        except httpx.TransportError as exc:
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, str(exc)) from exc

        if resp.status_code != 200:
            kind = _map_http_status(resp.status_code, resp.text)
            raise AttemptFailed(
                kind,
                PROVIDER,
                candidate.model,
                f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}",
                retry_after_s=_retry_after_hint(resp.headers, resp.text) if resp.status_code in (429, 402) else None,
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                f"Failed to parse JSON response: {exc}",
            ) from exc

        choices = data.get("choices", [])
        if not choices:
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "No choices returned in OpenRouter response",
            )

        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if not content or not content.strip():
            reasoning_tokens = (
                ((data.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
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

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        serving_model = data.get("model", candidate.model)
        notes = [f"served via OpenRouter: {serving_model}", *degradation_notes]

        return AdapterCompletion(
            text=content,
            usage=usage,
            provider=PROVIDER,
            model=serving_model,
            notes=notes,
        )

    async def health_check(self, model: Optional[str] = None) -> dict:
        """Perform a safe, authenticated health check against OpenRouter API.

        Never returns or logs the actual API key.
        """
        key = self._get_api_key()
        if not key or not key.strip():
            return {
                "configured": False,
                "authenticated": False,
                "model": model or self._default_model,
                "status": "not_configured",
                "error_code": "OPENROUTER_NOT_CONFIGURED",
                "message": "OPENROUTER_API_KEY is not set in environment or .env.",
            }

        target_model = model or os.environ.get("OPENROUTER_MODEL") or self._default_model
        client = await self._get_client()

        payload = {
            "model": target_model,
            "messages": [
                {
                    "role": "user",
                    "content": "Return exactly: BebshaX OpenRouter connection successful.",
                }
            ],
            "max_tokens": 30,
            "temperature": 0.0,
        }
        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "HTTP-Referer": "https://bebshax.ai",
            "X-Title": "BebshaX Health Diagnostic",
            "Content-Type": "application/json",
        }

        t0 = time.perf_counter()
        try:
            resp = await client.post(OPENROUTER_ENDPOINT, json=payload, headers=headers)
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        except httpx.TimeoutException:
            return {
                "configured": True,
                "authenticated": False,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_TIMEOUT",
                "message": "OpenRouter connection timed out after 30 seconds.",
            }
        except httpx.TransportError as exc:
            return {
                "configured": True,
                "authenticated": False,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_CONNECTION_ERROR",
                "message": f"Network transport error connecting to OpenRouter: {exc}",
            }

        if resp.status_code == 401 or resp.status_code == 403:
            return {
                "configured": True,
                "authenticated": False,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_AUTH_FAILED",
                "message": "OpenRouter authentication failed. Please verify OPENROUTER_API_KEY.",
            }

        if resp.status_code == 429:
            return {
                "configured": True,
                "authenticated": True,
                "model": target_model,
                "status": "rate_limited",
                "error_code": "OPENROUTER_RATE_LIMITED",
                "message": "OpenRouter rate limit reached or free credit exhausted.",
            }

        if resp.status_code == 404:
            return {
                "configured": True,
                "authenticated": True,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_MODEL_UNAVAILABLE",
                "message": f"Requested model '{target_model}' is not available on OpenRouter.",
            }

        if resp.status_code != 200:
            return {
                "configured": True,
                "authenticated": False,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_API_ERROR",
                "message": f"OpenRouter returned HTTP {resp.status_code}: {resp.text[:200]}",
            }

        try:
            data = resp.json()
            serving_model = data.get("model", target_model)
            choices = data.get("choices", [])
            reply_text = (
                choices[0].get("message", {}).get("content", "").strip() if choices else ""
            )
            return {
                "configured": True,
                "authenticated": True,
                "model": serving_model,
                "latency_ms": latency_ms,
                "status": "healthy",
                "verified_response": reply_text[:100],
                "message": "OpenRouter connected and verified successfully.",
            }
        except Exception as exc:
            return {
                "configured": True,
                "authenticated": True,
                "model": target_model,
                "status": "error",
                "error_code": "OPENROUTER_MALFORMED_RESPONSE",
                "message": f"Failed to parse OpenRouter JSON response: {exc}",
            }

