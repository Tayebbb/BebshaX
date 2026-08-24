"""OpenRouterAdapter — direct OpenRouter provider adapter (RULES.md R1).

Provides access to OpenRouter's vast multi-model routing table (DeepSeek-R1,
Llama-3.3-70B, Gemini 2.0 Flash, Claude, GPT-4o-mini, etc.).
"""

from __future__ import annotations

import os
import time
from typing import Optional
import httpx

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.types import LLMRequest, TokenUsage

PROVIDER = "openrouter"
DEFAULT_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
    "openrouter/auto",
]
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _map_http_status(status: int | None) -> FailureKind:
    if status == 429:
        return FailureKind.RATE_LIMITED
    if status in (401, 403):
        return FailureKind.AUTH_INVALID
    if status == 404:
        return FailureKind.MODEL_UNAVAILABLE
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
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._default_model = default_model
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_api_key(self) -> str | None:
        return self._api_key or os.environ.get("OPENROUTER_API_KEY")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

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
            for m in DEFAULT_MODELS
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
        try:
            resp = await client.post(OPENROUTER_ENDPOINT, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, str(exc)) from exc
        except httpx.TransportError as exc:
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, str(exc)) from exc

        if resp.status_code != 200:
            kind = _map_http_status(resp.status_code)
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

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        serving_model = data.get("model", candidate.model)
        notes = [f"served via OpenRouter: {serving_model}"]

        return AdapterCompletion(
            text=content,
            usage=usage,
            provider=PROVIDER,
            model=serving_model,
            notes=notes,
        )
