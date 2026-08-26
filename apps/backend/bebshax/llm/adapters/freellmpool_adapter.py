"""FreellmpoolAdapter — the ONLY module (with this package) allowed to import
freellmpool (RULES.md R1).

Design: freellmpool is exposed as ONE virtual route ("freellmpool/auto").
Its internal provider failover, quota tracking, and circuit breakers are reused
as-is; BebshaX-level fallback (e.g. → Ollama) happens across adapters in the
Phase-5 router. The concrete serving provider/model from each Reply is written
into AdapterCompletion so provenance never shows "auto".
"""

from __future__ import annotations

import httpx
from freellmpool import errors as fl_errors
from freellmpool.aio import AsyncPool

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.latency import attempt_timeout_s
from bebshax.llm.types import LLMRequest, TokenUsage

PROVIDER = "freellmpool"
VIRTUAL_MODEL = "auto"
# Pre-flight window for the virtual route: freellmpool learns real per-model
# limits itself and raises its own ContextWindowExceeded when nothing fits.
VIRTUAL_CONTEXT_WINDOW = 1_000_000


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


class FreellmpoolAdapter(ProviderAdapter):
    def __init__(self, pool: AsyncPool | None = None, routing: str | None = None) -> None:
        self._pool = pool  # injectable for tests; lazily created otherwise
        self._routing = routing  # freellmpool routing mode (None = its default)

    async def _get_pool(self) -> AsyncPool:
        if self._pool is None:
            self._pool = AsyncPool.from_default_config()
        return self._pool

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

    async def candidates(self) -> list[RouteCandidate]:
        # supports_json=True: the pool contains JSON-capable targets; strict
        # response_format enforcement is refined with the Phase-5 registry.
        # supports_tools=False until LLMRequest carries tool schemas.
        return [
            RouteCandidate(
                provider=PROVIDER,
                model=VIRTUAL_MODEL,
                context_window=VIRTUAL_CONTEXT_WINDOW,
                supports_json=True,
                supports_tools=False,
            )
        ]

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        pool = await self._get_pool()
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        # Per-attempt budget by task class: a queued free endpoint that cannot
        # answer an interactive request in time yields to the next candidate.
        kwargs: dict = {"timeout": attempt_timeout_s(request.task)}
        if request.max_output_tokens is not None:
            kwargs["max_tokens"] = request.max_output_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if self._routing is not None:
            kwargs["routing"] = self._routing

        try:
            reply = await pool.achat(messages, **kwargs)
        except fl_errors.ContextWindowExceeded as exc:  # subclass — catch first
            raise AttemptFailed(
                FailureKind.CONTEXT_WINDOW_EXCEEDED, PROVIDER, VIRTUAL_MODEL, str(exc)
            ) from exc
        except fl_errors.AllProvidersExhausted as exc:
            kind = (
                _map_http_status(exc.client_status)
                if getattr(exc, "client_status", None)
                else FailureKind.PROVIDER_UNAVAILABLE
            )
            raise AttemptFailed(kind, PROVIDER, VIRTUAL_MODEL, str(exc)) from exc
        except fl_errors.NoProvidersConfigured as exc:
            raise AttemptFailed(
                FailureKind.PROVIDER_UNAVAILABLE, PROVIDER, VIRTUAL_MODEL, str(exc)
            ) from exc
        except fl_errors.ProviderHTTPError as exc:
            raise AttemptFailed(
                _map_http_status(getattr(exc, "status", None)), PROVIDER, VIRTUAL_MODEL, str(exc)
            ) from exc
        except fl_errors.FreeLLMPoolError as exc:
            raise AttemptFailed(
                FailureKind.PROVIDER_UNAVAILABLE, PROVIDER, VIRTUAL_MODEL, str(exc)
            ) from exc
        except httpx.TimeoutException as exc:
            raise AttemptFailed(FailureKind.TIMEOUT, PROVIDER, VIRTUAL_MODEL, str(exc)) from exc
        except httpx.TransportError as exc:
            raise AttemptFailed(FailureKind.CONNECTION, PROVIDER, VIRTUAL_MODEL, str(exc)) from exc

        if not reply.text or not reply.text.strip():
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                reply.provider_id or PROVIDER,
                reply.model or VIRTUAL_MODEL,
                "empty response",
            )

        # Mechanical truncation signal: completion consumed the entire output
        # budget, so the reply is cut mid-thought (observed live: reasoning
        # models leak truncated chain-of-thought). Same policy as other
        # malformed responses: retry once, then advance.
        if (
            request.max_output_tokens is not None
            and reply.completion_tokens is not None
            and reply.completion_tokens >= request.max_output_tokens
        ):
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                reply.provider_id or PROVIDER,
                reply.model or VIRTUAL_MODEL,
                f"output truncated at max_tokens ({reply.completion_tokens}/{request.max_output_tokens})",
            )

        notes = [f"freellmpool internal attempts: {reply.attempts}"]
        if reply.cached:
            notes.append("served from freellmpool response cache")
        return AdapterCompletion(
            text=reply.text,
            usage=TokenUsage(
                input_tokens=reply.prompt_tokens, output_tokens=reply.completion_tokens
            ),
            provider=reply.provider_id or PROVIDER,
            model=reply.model or VIRTUAL_MODEL,
            notes=notes,
        )
