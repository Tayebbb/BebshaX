"""PoolRouter — the production LLMService.

task → pool (config) → candidates from the pool's adapters in preference
order → eligibility (capabilities + context estimate + cooldowns) → attempt
loop with per-failure-kind policies → cross-adapter fallback (pools end at
the local adapter; `emergency` starts there).

Ranking is pool order by default; `ranker` is the injection point — production
wires the §10 quota-aware ranker there. Cooldowns are in-memory
`(provider, model) → deadline`, restored from and mirrored to
`model_registry.cooldown_until` via bebshax.db.capacity_state.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from bebshax.llm.adapters.base import ProviderAdapter, RouteCandidate
from bebshax.llm.failures import FailureKind, LLMError
from bebshax.llm.pools import POOLS, TASK_POOL_MAP, PoolConfig
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.service import Entry, LLMService, attempt_candidates, filter_eligible
from bebshax.llm.types import LLMRequest, LLMResult, TaskType

DEFAULT_COOLDOWN_SECONDS = 60.0


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
        until = self._cooldown_until.get((cand.provider, cand.model))
        if until is not None and self._clock() < until:
            return f"cooling down for {until - self._clock():.0f}s more"
        return None

    def _start_cooldown(self, cand: RouteCandidate, kind: FailureKind) -> None:
        self._cooldown_until[(cand.provider, cand.model)] = (
            self._clock() + self._cooldown_seconds
        )
        if self._on_cooldown_change is not None:
            # fire-and-forget persistence — cooldown state must survive restarts
            self._on_cooldown_change(cand.provider, cand.model, self._cooldown_seconds)

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
                    entries: list[Entry] = []
                    for adapter_name in pool.adapters:
                        adapter = self._adapters.get(adapter_name)
                        if adapter is None:
                            continue
                        for cand in await adapter.candidates():
                            entries.append((adapter, cand))
                    if self._ranker is not None:
                        entries = self._ranker(entries)
                    entries = _apply_preference(entries, request, provenance)
                    eligible = filter_eligible(
                        entries, request, provenance, extra_skip_reason=self._cooling_reason
                    )
                    return await attempt_candidates(
                        eligible, request, provenance, on_cooldown=self._start_cooldown
                    )
                finally:
                    self._active_requests[pool_name] -= 1
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)
