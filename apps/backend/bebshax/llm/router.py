"""PoolRouter — the production LLMService.

task → pool (config) → candidates from the pool's adapters in preference
order → eligibility (capabilities + context estimate + cooldowns) → attempt
loop with per-failure-kind policies → cross-adapter fallback (pools end at
the local adapter; `emergency` starts there).

Ranking is pool order by default; `ranker` is the injection point — production
wires the §10 quota-aware ranker there. Cooldowns are in-memory
`(provider, model) → deadline` — or `(provider, "*")` when the failure policy
scopes the cooldown to the whole provider (account-level signals such as 429)
— restored from and mirrored to `model_registry.cooldown_until` via
bebshax.db.capacity_state.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing

from bebshax.llm.adapters.base import (
    ProviderAdapter,
    RouteCandidate,
    StreamDelta,
    StreamDone,
)
from bebshax.llm.failures import (
    FAILURE_POLICIES,
    AttemptFailed,
    FailureKind,
    LLMError,
)
from bebshax.llm.pools import POOLS, TASK_POOL_MAP, PoolConfig
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.service import (
    Entry,
    LLMService,
    attempt_candidates,
    exhaustion_error,
    filter_eligible,
    stamp_internal_error,
)
from bebshax.llm.types import LLMRequest, LLMResult, TaskType

DEFAULT_COOLDOWN_SECONDS = 60.0
PROVIDER_WIDE = "*"  # model slot of a provider-scoped cooldown key


def cooldown_key(cand: RouteCandidate, kind: FailureKind) -> tuple[str, str]:
    """(provider, model) for route-scoped policies, (provider, "*") for
    provider-scoped ones — the same key shape persists to model_registry."""
    if FAILURE_POLICIES[kind].cooldown_scope == "provider":
        return (cand.provider, PROVIDER_WIDE)
    return (cand.provider, cand.model)


def _compact_routes(entries: list[Entry]) -> str:
    return ", ".join(f"{cand.provider}/{cand.model}" for _, cand in entries)


def _apply_preference(
    entries: list[Entry], request: LLMRequest, provenance: ProvenanceRecord
) -> list[Entry]:
    """§7 model selection: stable-partition preferred routes to the front.
    Preference is advisory — never exclusive — so fallback to Auto is free."""
    if request.preferred_provider is None and request.preferred_model is None:
        return entries

    def _matches(entry: Entry) -> bool:
        cand = entry[1]
        return (
            request.preferred_provider is None or cand.provider == request.preferred_provider
        ) and (request.preferred_model is None or cand.model == request.preferred_model)

    preferred = [e for e in entries if _matches(e)]
    rest = [e for e in entries if not _matches(e)]
    provenance.routing_path.append(
        f"[preference {request.preferred_provider or '*'}/{request.preferred_model or '*'}: "
        f"{len(preferred)} route(s) prioritized]"
    )
    return preferred + rest


class PoolRouter(LLMService):
    def __init__(
        self,
        adapters: dict[str, ProviderAdapter],
        pools: dict[str, PoolConfig] | None = None,
        task_pool_map: dict[TaskType, str] | None = None,
        on_provenance: Callable[[ProvenanceRecord], None] | None = None,
        ranker: Callable[[list[Entry]], list[Entry]] | None = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        initial_cooldowns: dict[tuple[str, str], float] | None = None,
        on_cooldown_change: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self._adapters = adapters
        self._pools = pools if pools is not None else POOLS
        self._task_pool_map = task_pool_map if task_pool_map is not None else TASK_POOL_MAP
        self._on_provenance = on_provenance
        self._ranker = ranker
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        # absolute deadlines in `clock` time — CooldownStore.load_active() converts
        # wall→deadline; on_cooldown_change receives a DURATION in seconds
        self._cooldown_until: dict[tuple[str, str], float] = dict(initial_cooldowns or {})
        self._on_cooldown_change = on_cooldown_change

        for pool in self._pools.values():
            unknown = [name for name in pool.adapters if name not in adapters]
            if unknown:
                raise ValueError(f"pool '{pool.name}' references unknown adapter(s): {unknown}")
        self._semaphores = {
            name: asyncio.Semaphore(p.max_concurrency) for name, p in self._pools.items()
        }
        self._active_requests: dict[str, int] = {name: 0 for name in self._pools}

    def is_cooling(self, cand: RouteCandidate) -> bool:
        """Public cooling check — observability endpoints must not touch privates."""
        return self._cooling_reason(cand) is not None

    def pool_utilization(self) -> dict[str, dict[str, int]]:
        """Real per-pool concurrency snapshot: {pool: {max_concurrency, active_requests}}."""
        return {
            name: {
                "max_concurrency": pool.max_concurrency,
                "active_requests": self._active_requests[name],
            }
            for name, pool in self._pools.items()
        }

    def _cooling_reason(self, cand: RouteCandidate) -> str | None:
        now = self._clock()
        for key in ((cand.provider, cand.model), (cand.provider, PROVIDER_WIDE)):
            until = self._cooldown_until.get(key)
            if until is not None and now < until:
                scope = " (provider-wide)" if key[1] == PROVIDER_WIDE else ""
                return f"cooling down for {until - now:.0f}s more{scope}"
        return None

    def _start_cooldown(self, cand: RouteCandidate, kind: FailureKind) -> None:
        provider, model = cooldown_key(cand, kind)
        self._cooldown_until[(provider, model)] = self._clock() + self._cooldown_seconds
        if self._on_cooldown_change is not None:
            # fire-and-forget persistence — cooldown state must survive restarts;
            # provider-scoped cooldowns persist with model "*" and load back as-is
            self._on_cooldown_change(provider, model, self._cooldown_seconds)

    async def _eligible_entries(
        self, pool: PoolConfig, request: LLMRequest, provenance: ProvenanceRecord
    ) -> list[Entry]:
        entries: list[Entry] = []
        for adapter_name in pool.adapters:
            adapter = self._adapters.get(adapter_name)
            if adapter is None:
                continue
            for cand in await adapter.candidates():
                entries.append((adapter, cand))
        if self._ranker is not None:
            ranked = self._ranker(entries)
            if [c for _, c in ranked] != [c for _, c in entries]:
                provenance.routing_path.append(
                    f"[ranker reordered: {_compact_routes(entries)} -> {_compact_routes(ranked)}]"
                )
            entries = ranked
        entries = _apply_preference(entries, request, provenance)
        return filter_eligible(
            entries, request, provenance, extra_skip_reason=self._cooling_reason
        )

    async def complete(self, request: LLMRequest) -> LLMResult:
        pool_name = self._task_pool_map.get(request.task)
        if pool_name is None or pool_name not in self._pools:
            raise LLMError(f"no pool mapped for task {request.task}")
        pool = self._pools[pool_name]

        provenance = ProvenanceRecord(
            request_id=request.request_id,
            task=request.task.value,
            pool=pool_name,
            persona_id=request.persona_id,
            conversation_id=request.conversation_id,
        )
        started = time.perf_counter()
        try:
            async with self._semaphores[pool_name]:
                self._active_requests[pool_name] += 1
                try:
                    eligible = await self._eligible_entries(pool, request, provenance)
                    return await attempt_candidates(
                        eligible,
                        request,
                        provenance,
                        on_cooldown=self._start_cooldown,
                        skip_reason=self._cooling_reason,
                    )
                finally:
                    self._active_requests[pool_name] -= 1
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamDelta | LLMResult]:
        """Streaming complete(): yields StreamDelta chunks, then the final
        LLMResult (canonical text + full provenance).

        Fallback semantics: candidates that fail BEFORE their first delta are
        skipped per the same failure policies; once a route has produced text
        the stream is committed to it — a mid-answer swap would splice two
        different personas' voices (R2), so the failure surfaces instead.
        """
        pool_name = self._task_pool_map.get(request.task)
        if pool_name is None or pool_name not in self._pools:
            raise LLMError(f"no pool mapped for task {request.task}")
        pool = self._pools[pool_name]

        provenance = ProvenanceRecord(
            request_id=request.request_id,
            task=request.task.value,
            pool=pool_name,
            persona_id=request.persona_id,
            conversation_id=request.conversation_id,
        )
        started = time.perf_counter()
        try:
            async with self._semaphores[pool_name]:
                self._active_requests[pool_name] += 1
                try:
                    eligible = await self._eligible_entries(pool, request, provenance)

                    attempt_no = 0
                    for adapter, cand in eligible:
                        cooling = self._cooling_reason(cand)  # started mid-request?
                        if cooling is not None:
                            provenance.routing_path.append(
                                f"{cand.provider}/{cand.model} [skipped: {cooling}]"
                            )
                            continue
                        same_route_retries = 0
                        while True:
                            attempt_no += 1
                            record = AttemptRecord(
                                attempt_number=attempt_no, provider=cand.provider, model=cand.model
                            )
                            provenance.attempts.append(record)
                            t0 = time.perf_counter()
                            committed = False
                            try:
                                async with aclosing(adapter.stream(cand, request)) as adapter_stream:
                                    async for event in adapter_stream:
                                        if isinstance(event, StreamDelta):
                                            committed = True
                                            yield event
                                        elif isinstance(event, StreamDone):
                                            completion = event.completion
                                            record.latency_ms = (time.perf_counter() - t0) * 1000
                                            record.success = True
                                            if (completion.provider, completion.model) != (
                                                cand.provider,
                                                cand.model,
                                            ):
                                                record.via = f"{cand.provider}/{cand.model}"
                                            record.provider = completion.provider
                                            record.model = completion.model
                                            record.notes = list(completion.notes)
                                            provenance.success = True
                                            provenance.served_by_provider = completion.provider
                                            provenance.served_by_model = completion.model
                                            provenance.input_tokens = completion.usage.input_tokens
                                            provenance.output_tokens = completion.usage.output_tokens
                                            yield LLMResult(
                                                text=completion.text,
                                                provider=completion.provider,
                                                model=completion.model,
                                                usage=completion.usage,
                                                provenance=provenance,
                                            )
                                            return
                                # Stream ended without StreamDone: treat as malformed.
                                raise AttemptFailed(
                                    FailureKind.MALFORMED_RESPONSE,
                                    cand.provider,
                                    cand.model,
                                    "stream ended without a terminal completion",
                                )
                            except (GeneratorExit, asyncio.CancelledError):
                                # Consumer abort — but closing AFTER StreamDone was
                                # consumed lands here too (GeneratorExit at the final
                                # yield), so never overwrite a successful record.
                                if not record.success:
                                    record.latency_ms = (time.perf_counter() - t0) * 1000
                                    record.failure_detail = "aborted by consumer"
                                raise
                            except AttemptFailed as failure:
                                record.latency_ms = (time.perf_counter() - t0) * 1000
                                record.failure_kind = failure.kind
                                record.failure_detail = failure.detail
                                policy = FAILURE_POLICIES[failure.kind]
                                if policy.cooldown_route:
                                    self._start_cooldown(cand, failure.kind)
                                # Deliberate order difference from attempt_candidates:
                                # a committed route must never retry or advance — the
                                # user already saw its words (R2).
                                if committed or not policy.try_next_candidate:
                                    raise
                                if policy.retry_same_once and same_route_retries == 0:
                                    same_route_retries += 1
                                    record.fallback_reason = "retrying same route once"
                                    continue
                                record.fallback_reason = f"advancing after {failure.kind}"
                                break
                            except Exception as exc:  # adapter bug — surface, never advance
                                raise stamp_internal_error(record, exc, t0) from exc
                    raise exhaustion_error(provenance, request)
                finally:
                    self._active_requests[pool_name] -= 1
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)
