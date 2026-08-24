"""PoolRouter — the production LLMService.

task → pool (config) → candidates from the pool's adapters in preference
order → eligibility (capabilities + context estimate + cooldowns) → attempt
loop with per-failure-kind policies → cross-adapter fallback (pools end at
the local adapter; `emergency` starts there).

Ranking is pool order for now; `ranker` is the injection point where the
Phase-6 model registry's quality/latency/health scores plug in.
Cooldowns are in-memory `(provider, model) → until`; DB persistence is
Phase 6 scope.
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
    ) -> None:
        self._adapters = adapters
        self._pools = pools if pools is not None else POOLS
        self._task_pool_map = task_pool_map if task_pool_map is not None else TASK_POOL_MAP
        self._on_provenance = on_provenance
        self._ranker = ranker
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._cooldown_until: dict[tuple[str, str], float] = {}

        for pool in self._pools.values():
            unknown = [name for name in pool.adapters if name not in adapters]
            if unknown:
                import warnings
                warnings.warn(
                    f"pool '{pool.name}' references adapter(s) not in adapters dict: {unknown} — they will be skipped",
                    stacklevel=2,
                )
        self._semaphores = {
            name: asyncio.Semaphore(p.max_concurrency) for name, p in self._pools.items()
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
                entries: list[Entry] = []
                for adapter_name in pool.adapters:
                    adapter = self._adapters.get(adapter_name)
                    if adapter is None:
                        continue  # adapter not configured (e.g., openrouter key not set)
                    for cand in await adapter.candidates():
                        entries.append((adapter, cand))
                if self._ranker is not None:
                    entries = self._ranker(entries)
                eligible = filter_eligible(
                    entries, request, provenance, extra_skip_reason=self._cooling_reason
                )
                return await attempt_candidates(
                    eligible, request, provenance, on_cooldown=self._start_cooldown
                )
        finally:
            provenance.total_latency_ms = (time.perf_counter() - started) * 1000
            if self._on_provenance is not None:
                self._on_provenance(provenance)
