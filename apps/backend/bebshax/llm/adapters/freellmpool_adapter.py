"""FreellmpoolAdapter — the ONLY module (with this package) allowed to import
freellmpool (RULES.md R1).

The virtual route represents only configured, context-verified primary targets.
Supported SDK construction, transport and event hooks enforce app-owned policy;
the outer router owns independent OpenRouter fallback. Reported model identity
and per-target observations remain separate from requested model names.
"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
from freellmpool import errors as fl_errors
from freellmpool.aio import AsyncPool
from freellmpool.models import Provider
from freellmpool.quota import QuotaStore
from freellmpool.router import Pool

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.adapters.freellmpool_transport import AttemptQuota, DispatchAborted, DispatchState, GovernedTransport, dispatch_state
from bebshax.llm.adapters.provider_policy import approved_primary_providers, configured_json_models, load_primary_catalog
from bebshax.llm.estimator import DEFAULT_EXPECTED_OUTPUT_TOKENS, estimate_request_tokens
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import get_dispatch_approval
from bebshax.llm.latency import DeadlineExpired, await_before, remaining_attempt_timeout_s
from bebshax.llm.types import LLMRequest, TokenUsage
from bebshax.llm.validation import validate_text

PROVIDER = "freellmpool"
VIRTUAL_MODEL = "auto"


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
    streaming_mode = "buffered"
    manages_cooldowns = True
    remote_processing = True

    def __init__(
        self, pool: AsyncPool | None = None, routing: str | None = None, *,
        providers: list[Provider] | None = None, env: dict[str, str] | None = None,
        quota: QuotaStore | None = None, apost=None, provider_config: Path | None = None,
        quota_remaining: Callable[[str], float] | None = None,
        initial_cooldowns: dict[tuple[str, str], float] | None = None,
        on_cooldown_change: Callable[[str, str, float], None] | None = None,
        json_models: frozenset[tuple[str, str]] | None = None,
        reserve_attempt: Callable[[str], str | None] | None = None,
    ) -> None:
        self._pool = pool  # injectable for tests; lazily created otherwise
        self._routing = routing  # freellmpool routing mode (None = its default)
        self._providers = providers
        self._json_models = json_models
        self._env = env
        self._quota = quota
        self._apost = apost
        self._provider_config = provider_config or Path(__file__).resolve().parents[5] / "providers.toml"
        self._transport: GovernedTransport | None = None
        self._quota_remaining = quota_remaining
        self._reserve_attempt = reserve_attempt
        self._initial_cooldowns = dict(initial_cooldowns or {})
        self._on_cooldown_change = on_cooldown_change

    async def _get_pool(self) -> AsyncPool:
        if self._pool is None:
            if self._providers is None:
                try:
                    catalog = load_primary_catalog(self._provider_config)
                    if self._json_models is None:
                        self._json_models = configured_json_models(self._provider_config)
                except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
                    raise AttemptFailed(FailureKind.PROVIDER_UNAVAILABLE, PROVIDER, VIRTUAL_MODEL, "application-owned primary catalog unavailable or invalid", provider_fault=False) from exc
            else:
                catalog = self._providers
                if self._json_models is None:
                    self._json_models = frozenset()
            approved = approved_primary_providers(catalog)
            if self._env is None:
                names = {name for provider in approved for name in (provider.key_env, *provider.extra_env) if name}
                env = {name: os.environ[name] for name in names if name in os.environ}
            else:
                env = dict(self._env)
            configured = [provider for provider in approved if provider.is_configured(env)]
            self._transport = GovernedTransport(
                configured, apost=self._apost, quota_remaining=self._quota_remaining,
                initial_cooldowns=self._initial_cooldowns, on_cooldown_change=self._on_cooldown_change,
                json_models=self._json_models,
                reserve_attempt=self._reserve_attempt,
            )
            quota = self._quota or QuotaStore(path=self._provider_config.parent / ".cache" / "llm" / "freellmpool-quota.json")
            governed = Pool(configured, env=env, quota=cast(QuotaStore, AttemptQuota(quota)), cache=None, routing=self._routing or "fair", on_event=self._transport.on_event)
            self._transport.pool = governed
            self._pool = AsyncPool(governed, apost=self._transport.post)
        return self._pool

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
        if self._transport is not None:
            await self._transport.aclose()
            self._transport = None

    async def seed_metrics(self, observations: list[tuple[str, str, float]]) -> int:
        """Replay chronological endpoint measurements for verified primary targets only."""
        pool = await self._get_pool()
        allowed = {
            (provider.id, model.name)
            for provider in approved_primary_providers(pool.providers)
            for model in provider.models if model.context is not None and model.context > 0
        } if isinstance(pool, AsyncPool) else None
        applied = 0
        for provider, model, latency_ms in observations:
            if allowed is not None and (provider, model) not in allowed:
                continue
            if not math.isfinite(latency_ms) or latency_ms < 0:
                continue
            pool.metrics.record_success(f"{provider}/{model}", float(latency_ms))
            applied += 1
        return applied

    async def _candidates(self, request: LLMRequest | None) -> list[RouteCandidate]:
        pool = await self._get_pool()
        if isinstance(pool, AsyncPool):
            if self._transport is None:
                return []
            approval = get_dispatch_approval()
            configured = approved_primary_providers(pool.providers, allowed_provider_ids=approval.provider_ids if approval is not None else None)
            models = [
                (provider.id, model) for provider in configured for model in provider.models
                if model.context is not None and model.context > 0
                and (request is None or not request.json_mode or (provider.id, model.name) in (self._json_models or frozenset()))
                and (request is None or (
                    self._transport.cooling_remaining(provider.id, model.name) <= 0
                    and (self._quota_remaining is None or self._quota_remaining(provider.id) > 0)
                    and not pool.quota.over_budget(provider.id, model.name, model.rpd)
                ))
            ]
            windows = [model.context for _, model in models if model.context is not None]
            if not windows:
                return []
            window = max(windows)
            supports_json = any((provider_id, model.name) in (self._json_models or frozenset()) for provider_id, model in models)
        else:
            window = 128_000
            supports_json = True
        return [
            RouteCandidate(
                provider=PROVIDER,
                model=VIRTUAL_MODEL,
                context_window=window,
                supports_json=supports_json,
                supports_tools=False,
            )
        ]

    async def candidates(self) -> list[RouteCandidate]:
        return await self._candidates(None)

    async def candidates_for(self, request: LLMRequest) -> list[RouteCandidate]:
        return await self._candidates(request)

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        pool = await self._get_pool()
        if request.tools_required:
            raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, VIRTUAL_MODEL, "tool execution contract is unavailable")
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        # Per-attempt budget by task class: a queued free endpoint that cannot
        # answer an interactive request in time yields to the next candidate.
        # freellmpool applies `timeout` PER INNER TARGET, so its internal
        # failover could stretch one attempt to N×budget — the outer wait_for
        # makes the budget hold for the attempt as a whole.
        budget_s = remaining_attempt_timeout_s(request.task)
        kwargs: dict = {"timeout": budget_s, "max_tokens": request.max_output_tokens if request.max_output_tokens is not None else DEFAULT_EXPECTED_OUTPUT_TOKENS}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if self._routing is not None:
            kwargs["routing"] = self._routing

        state = DispatchState(request=request, deadline=asyncio.get_running_loop().time() + budget_s)
        if isinstance(pool, AsyncPool):
            if self._transport is None:
                raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, VIRTUAL_MODEL, "unmanaged AsyncPool is unsupported; inject providers and apost instead")
            needed = estimate_request_tokens(request)
            approval = get_dispatch_approval()
            configured = approved_primary_providers(pool.providers, allowed_provider_ids=approval.provider_ids if approval is not None else None)
            if request.json_mode and not any((provider.id, model.name) in (self._json_models or frozenset()) for provider in configured for model in provider.models):
                raise AttemptFailed(FailureKind.CAPABILITY_UNSUPPORTED, PROVIDER, VIRTUAL_MODEL, "JSON capability lacks explicit verified model metadata", provider_fault=False)
            eligible = [provider.id for provider in configured if any(
                model.context is not None and model.context >= needed and self._transport.cooling_remaining(provider.id, model.name) <= 0
                and (not request.json_mode or (provider.id, model.name) in (self._json_models or frozenset()))
                for model in provider.models
            )]
            if not eligible:
                hint = max((self._transport.cooling_remaining(provider.id, model.name) for provider in configured for model in provider.models), default=0.0)
                raise AttemptFailed(FailureKind.PROVIDER_UNAVAILABLE, PROVIDER, VIRTUAL_MODEL, "no verified context-fitting, non-cooling primary targets", retry_after_s=hint or None, provider_fault=False)
            kwargs["providers"] = eligible
        elif request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        token = dispatch_state.set(state)
        try:
            reply = await await_before(pool.achat(messages, **kwargs), state.deadline)
        except DispatchAborted as exc:
            raise exc.failure from exc
        except asyncio.CancelledError as exc:
            setattr(exc, "observations", list(state.observations))
            raise
        except (DeadlineExpired, asyncio.TimeoutError) as exc:
            raise AttemptFailed(
                FailureKind.TIMEOUT, PROVIDER, VIRTUAL_MODEL, "attempt budget exceeded", observations=state.observations, provider_fault=False
            ) from exc
        except fl_errors.ContextWindowExceeded as exc:  # subclass — catch first
            raise AttemptFailed(
                FailureKind.CONTEXT_WINDOW_EXCEEDED, PROVIDER, VIRTUAL_MODEL, str(exc)
            ) from exc
        except fl_errors.AllProvidersExhausted as exc:
            kinds = {observation.failure_kind for observation in state.observations if observation.failure_kind is not None}
            kind = next(iter(kinds)) if len(kinds) == 1 else (
                _map_http_status(exc.client_status)
                if getattr(exc, "client_status", None)
                else FailureKind.PROVIDER_UNAVAILABLE
            )
            hint = max((observation.retry_after_s or 0.0 for observation in state.observations), default=0.0)
            raise AttemptFailed(kind, PROVIDER, VIRTUAL_MODEL, "primary targets exhausted", retry_after_s=hint or None, observations=state.observations) from exc
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
        finally:
            dispatch_state.reset(token)

        if not reply.text or not reply.text.strip():
            raise AttemptFailed(
                FailureKind.MALFORMED_RESPONSE,
                reply.provider_id or PROVIDER,
                reply.model or VIRTUAL_MODEL,
                "empty response",
            )

        winner = next((observation for observation in reversed(state.observations) if observation.outcome == "succeeded"), None)
        raw_choices = reply.raw.get("choices") if isinstance(reply.raw, dict) else None
        finish_reason = winner.finish_reason if winner is not None else (
            raw_choices[0].get("finish_reason") if isinstance(raw_choices, list) and raw_choices and isinstance(raw_choices[0], dict) else None
        )
        validate_text(reply.text, request, reply.provider_id or PROVIDER, reply.model or "unknown", finish_reason=finish_reason)

        notes = [f"freellmpool internal attempts: {reply.attempts}"]
        notes.extend([f"requested model: {reply.model}", f"finish_reason: {finish_reason or 'unknown'}", "buffered SDK completion; no native async streaming"])
        if reply.cached:
            notes.append("served from freellmpool response cache")
        return AdapterCompletion(
            text=reply.text,
            usage=TokenUsage(
                input_tokens=reply.prompt_tokens, output_tokens=reply.completion_tokens
            ),
            provider=reply.provider_id or PROVIDER,
            model=(winner.reported_model or "unknown") if winner is not None else (reply.model or "unknown"),
            notes=notes,
            cached=bool(reply.cached),
            finish_reason=finish_reason,
            latency_ms=winner.latency_ms if winner is not None else None,
            observations=state.observations,
        )
