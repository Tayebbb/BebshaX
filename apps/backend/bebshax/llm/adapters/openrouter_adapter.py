"""OpenRouterAdapter — direct OpenRouter provider adapter (RULES.md R1).

Provides access to OpenRouter's vast multi-model routing table (DeepSeek-R1,
Llama-3.3-70B, Gemini 2.0 Flash, Claude, GPT-4o-mini, etc.).
"""

from __future__ import annotations

import os
import re
import time
from typing import Optional
import httpx

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.latency import attempt_timeout_s
from bebshax.llm.types import LLMRequest, TokenUsage

PROVIDER = "openrouter"
# Measured-fast first (session data 2026-08-26). deepseek-r1 (CoT) and other
# reasoning-heavy free routes are intentionally NOT in the defaults — they
# burned 100s+ per interactive turn; pin them explicitly when needed.
# `openrouter/auto` is deliberately absent: it routes to PAID models, which
# breaks the $0 thesis (an operator can still pin it via BEBSHAX_OPENROUTER_MODELS).
DEFAULT_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
]
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
RESPONSE_FORMAT_DROPPED_NOTE = "response_format dropped after 400"

# OpenRouter reports prompt overflow as 400 (sometimes 413) with a prose body,
# e.g. "This endpoint's maximum context length is 8192 tokens".
_CONTEXT_OVERFLOW_BODY_RE = re.compile(
    r"context|maximum.*tokens|too long|token limit", re.IGNORECASE | re.DOTALL
)


def _configured_models() -> list[str]:
    """Model list — BEBSHAX_OPENROUTER_MODELS (comma-separated) overrides the
    defaults above. Free-tier catalogs drift; operators repoint without a
    release. Adapter-local env read, same pattern as OLLAMA_API_BASE (R1)."""
    raw = os.environ.get("BEBSHAX_OPENROUTER_MODELS", "")
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or list(DEFAULT_MODELS)


def _is_context_overflow_body(body: str | None) -> bool:
    return bool(body) and _CONTEXT_OVERFLOW_BODY_RE.search(body) is not None


def _map_http_status(status: int | None, body: str | None = None) -> FailureKind:
    if status == 429:
        return FailureKind.RATE_LIMITED
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


class OpenRouterAdapter(ProviderAdapter):
    """Adapter for OpenRouter chat completions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "meta-llama/llama-3.3-70b-instruct:free",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

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
        """Models this adapter would offer (env override or defaults) — no network."""
        return _configured_models()

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

        return [
            RouteCandidate(
                provider=PROVIDER,
                model=m,
                context_window=128_000,
                supports_json=True,
                supports_tools=False,
            )
            for m in _configured_models()
        ]

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

        headers = {
            "Authorization": f"Bearer {key.strip()}",
            "HTTP-Referer": "https://bebshax.ai",
            "X-Title": "BebshaX AI Persona Validation",
            "Content-Type": "application/json",
        }

        t0 = time.perf_counter()
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
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                PROVIDER,
                candidate.model,
                "Empty text in OpenRouter message choice",
            )

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

