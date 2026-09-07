"""OllamaAdapter — local reliability fallback (RULES.md R1 boundary module).

Uses Ollama's NATIVE /api/chat instead of its OpenAI-compat endpoint (spec
deviation, recorded in the Phase 4 log): only the native API accepts
options.num_ctx. Without pinning num_ctx to the request size, the Ollama
runtime silently truncates prompts beyond its default context — which would
violate R2 (never silently truncate). Native responses also carry exact token
counts. Talks plain httpx — no SDK dependency (R8).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator, Callable

import httpx

from bebshax.llm.adapters.base import (
    AdapterCompletion,
    ProviderAdapter,
    RouteCandidate,
    StreamDelta,
    StreamDone,
    StreamEvent,
)
from bebshax.llm.estimator import estimate_request_tokens
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.types import LLMRequest, TokenUsage

PROVIDER = "ollama"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONTEXT_FALLBACK = 8192
# 4 GB VRAM: huge contexts force CPU offload/OOM, so advertised windows are capped.
DEFAULT_MAX_CONTEXT_CAP = 16384
_NUM_CTX_FLOOR = 4096
# An unreachable daemon is remembered for this long so concurrent requests do
# not each re-probe /api/tags while holding a pool semaphore slot.
NEGATIVE_DISCOVERY_TTL_S = 30.0


def _ladder_rung(estimate: int) -> int:
    """Smallest power-of-two rung (from the floor) that is >= estimate.

    Ollama reloads the model whenever num_ctx changes, so sizing to a coarse
    ladder keeps reloads rare; the rung is never below the estimate."""
    rung = _NUM_CTX_FLOOR
    while rung < estimate:
        rung *= 2
    return rung


def _required_ctx(request: LLMRequest) -> int:
    """Ladder rung for the SHARED pre-flight estimate (bebshax.llm.estimator) —
    no private chars/N heuristic, so Bangla and English size identically here
    and in the router's eligibility check."""
    return _ladder_rung(estimate_request_tokens(request))


def _choose_num_ctx(estimate: int, window: int) -> int:
    """num_ctx for a model whose ladder tops out at its advertised window:
    the smallest rung >= estimate, or the window itself when no rung fits
    below it. Callers guarantee estimate <= window, so the result is never
    below the estimate (R2: never let the runtime truncate)."""
    return min(_ladder_rung(estimate), window)


class OllamaAdapter(ProviderAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str | None = None,
        max_context_cap: int = DEFAULT_MAX_CONTEXT_CAP,
        request_timeout: float = 180.0,
        tags_ttl: float = 60.0,
        negative_ttl: float = NEGATIVE_DISCOVERY_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url or os.environ.get("OLLAMA_API_BASE", DEFAULT_BASE_URL)
        self._client = client or httpx.AsyncClient(base_url=self._base_url)
        self._max_context_cap = max_context_cap
        self._request_timeout = request_timeout
        self._tags_ttl = tags_ttl
        self._negative_ttl = negative_ttl
        self._clock = clock
        self._candidates_cache: tuple[float, list[RouteCandidate]] | None = None
        self._unreachable_until: float | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def candidates(self) -> list[RouteCandidate]:
        now = self._clock()
        if self._candidates_cache and now - self._candidates_cache[0] < self._tags_ttl:
            return list(self._candidates_cache[1])
        if self._unreachable_until is not None and now < self._unreachable_until:
            return []  # daemon was unreachable moments ago — don't re-probe per request
        try:
            tags = (await self._client.get("/api/tags", timeout=10.0)).json().get("models", [])
        except (httpx.HTTPError, ValueError):
            self._unreachable_until = now + self._negative_ttl
            return []  # daemon down → this adapter simply contributes no routes
        self._unreachable_until = None

        entries: list[tuple[int, RouteCandidate]] = []
        for m in tags:
            name = m.get("name", "")
            if not name:
                continue
            window = min(await self._model_context(name), self._max_context_cap)
            entries.append(
                (
                    m.get("size", 0),
                    RouteCandidate(
                        provider=PROVIDER,
                        model=name,
                        context_window=window,
                        supports_json=True,
                        supports_tools=False,
                    ),
                )
            )
        entries.sort(key=lambda e: e[0])  # smaller = faster on 4 GB VRAM → prefer first
        result = [cand for _, cand in entries]
        self._candidates_cache = (now, result)
        return list(result)

    async def _model_context(self, model: str) -> int:
        try:
            resp = await self._client.post("/api/show", json={"model": model}, timeout=10.0)
            info = resp.json().get("model_info", {})
            for key, value in info.items():
                if key.endswith(".context_length") and isinstance(value, int):
                    return value
        except (httpx.HTTPError, ValueError):
            pass
        return DEFAULT_CONTEXT_FALLBACK

    def _sized_options(self, candidate: RouteCandidate, request: LLMRequest) -> tuple[int, dict]:
        """(num_ctx, options) for a request, or AttemptFailed(CONTEXT_WINDOW_EXCEEDED)
        when the shared estimate exceeds the advertised window — refuse rather
        than let Ollama truncate (R2). Policy advances the chain."""
        estimate = estimate_request_tokens(request)
        if estimate > candidate.context_window:
            raise AttemptFailed(
                FailureKind.CONTEXT_WINDOW_EXCEEDED,
                PROVIDER,
                candidate.model,
                f"needs ~{estimate} tokens > window {candidate.context_window}",
            )
        num_ctx = _choose_num_ctx(estimate, candidate.context_window)
        options: dict = {"num_ctx": num_ctx}
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if request.temperature is not None:
            options["temperature"] = request.temperature
        return num_ctx, options

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        num_ctx, options = self._sized_options(candidate, request)

        try:
            resp = await self._client.post(
                "/api/chat",
                json={
                    "model": candidate.model,
                    "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                    "stream": False,
                    "options": options,
                },
                timeout=self._request_timeout,
            )
        except httpx.TimeoutException as exc:
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, str(exc)) from exc
        except httpx.TransportError as exc:
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, str(exc)) from exc

        if resp.status_code == 404:
            raise AttemptFailed(
                FailureKind.MODEL_UNAVAILABLE, PROVIDER, candidate.model, resp.text[:200]
            )
        if resp.status_code >= 500:
            raise AttemptFailed(
                FailureKind.SERVER_ERROR, PROVIDER, candidate.model, resp.text[:200]
            )
        if resp.status_code != 200:
            raise AttemptFailed(
                FailureKind.PROVIDER_UNAVAILABLE,
                PROVIDER,
                candidate.model,
                f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "invalid JSON body"
            ) from exc

        text = (data.get("message") or {}).get("content", "")
        if not text or not text.strip():
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "empty response"
            )

        notes = [f"num_ctx={num_ctx}"]
        done_reason = data.get("done_reason")
        if done_reason and done_reason != "stop":
            notes.append(f"done_reason={done_reason}")
        return AdapterCompletion(
            text=text,
            usage=TokenUsage(
                input_tokens=data.get("prompt_eval_count"),
                output_tokens=data.get("eval_count"),
            ),
            provider=PROVIDER,
            model=data.get("model", candidate.model),
            notes=notes,
        )

    async def stream(
        self, candidate: RouteCandidate, request: LLMRequest
    ) -> AsyncIterator[StreamEvent]:
        """Native NDJSON streaming from /api/chat (stream=true)."""
        num_ctx, options = self._sized_options(candidate, request)

        parts: list[str] = []
        final: dict | None = None
        try:
            async with self._client.stream(
                "POST",
                "/api/chat",
                json={
                    "model": candidate.model,
                    "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                    "stream": True,
                    "options": options,
                },
                timeout=self._request_timeout,
            ) as resp:
                if resp.status_code == 404:
                    raise AttemptFailed(
                        FailureKind.MODEL_UNAVAILABLE, PROVIDER, candidate.model, "model not found"
                    )
                if resp.status_code != 200:
                    raise AttemptFailed(
                        FailureKind.SERVER_ERROR if resp.status_code >= 500 else FailureKind.PROVIDER_UNAVAILABLE,
                        PROVIDER,
                        candidate.model,
                        f"HTTP {resp.status_code}",
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError as exc:
                        raise AttemptFailed(
                            FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model,
                            "invalid NDJSON stream line",
                        ) from exc
                    # Ollama can emit {"error": ...} mid-stream AFTER HTTP 200
                    # (e.g. runner OOM) — a partial answer must never pass as
                    # a completed reply (R2).
                    if chunk.get("error"):
                        raise AttemptFailed(
                            FailureKind.SERVER_ERROR, PROVIDER, candidate.model,
                            f"mid-stream error: {str(chunk['error'])[:200]}",
                        )
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        parts.append(piece)
                        yield StreamDelta(text=piece)
                    if chunk.get("done"):
                        final = chunk
                        break
        except httpx.TimeoutException as exc:
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, candidate.model, str(exc)) from exc
        except httpx.TransportError as exc:
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, candidate.model, str(exc)) from exc

        if final is None:
            # Connection closed without done:true — whatever we streamed is a
            # truncated fragment, not the persona's answer.
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model,
                "stream ended without done marker",
            )
        text = "".join(parts)
        if not text.strip():
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE, PROVIDER, candidate.model, "empty stream"
            )
        notes = [f"num_ctx={num_ctx}", "streamed"]
        done_reason = final.get("done_reason")
        if done_reason and done_reason != "stop":
            notes.append(f"done_reason={done_reason}")
        yield StreamDone(
            completion=AdapterCompletion(
                text=text,
                usage=TokenUsage(
                    input_tokens=final.get("prompt_eval_count"),
                    output_tokens=final.get("eval_count"),
                ),
                provider=PROVIDER,
                model=final.get("model", candidate.model),
                notes=notes,
            )
        )
