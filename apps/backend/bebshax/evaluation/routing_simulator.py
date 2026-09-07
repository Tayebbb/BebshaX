"""Chaos simulation harness for evaluating LLM routing strategies.

What this measures: the router's CONTROL FLOW under scripted failures — how
many requests still get served, how many fallbacks each strategy burns,
whether context overflow is refused. FakeAdapter latencies are injected
sleeps and its replies carry no real tokens, so results are labelled
``kind="router_control_flow_simulation"`` and ``avg_tokens_per_sec`` is
None: nothing here is a provider throughput measurement.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Sequence

from bebshax.evaluation.strategies import RoutingStrategy, StrategyRankerFactory
from bebshax.evaluation.types import StrategyMetricResult
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate
from bebshax.llm.failures import AttemptFailed, ContextWindowExceeded, FailureKind, LLMError
from bebshax.llm.pools import POOLS, TASK_POOL_MAP
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import LLMRequest, TaskType


class ChaosFakeAdapter(FakeAdapter):
    """FakeAdapter with configurable chaos failure rates and latency injection."""

    def __init__(
        self,
        name: str,
        candidates: Sequence[RouteCandidate],
        failure_prob: float = 0.0,
        latency_ms: float = 10.0,
        fail_kind: FailureKind = FailureKind.RATE_LIMITED,
    ) -> None:
        routes = [FakeRoute(candidate=cand) for cand in candidates]
        super().__init__(routes=routes)
        self.name = name
        self.failure_prob = failure_prob
        self.latency_ms = latency_ms
        self.fail_kind = fail_kind

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        if random.random() < self.failure_prob:
            raise AttemptFailed(
                kind=self.fail_kind,
                provider=candidate.provider,
                model=candidate.model,
                detail=f"Chaos failure on {self.name}/{candidate.model}",
            )
        return await super().complete(candidate, request)


class RoutingChaosSimulator:
    """Runs workloads against PoolRouter with injected chaos to compare routing strategies."""

    def __init__(
        self,
        request_count: int = 35,
        seed: int = 42,
    ) -> None:
        self.request_count = request_count
        self.seed = seed

    def _setup_adapters(self) -> dict[str, ChaosFakeAdapter]:
        random.seed(self.seed)
        adapters = {
            # Keyless-openrouter equivalent: registered, contributes no routes.
            "openrouter": ChaosFakeAdapter(
                name="openrouter",
                candidates=[],
                failure_prob=0.0,
                latency_ms=0.0,
                fail_kind=FailureKind.PROVIDER_UNAVAILABLE,
            ),
            "freellmpool": ChaosFakeAdapter(
                name="freellmpool",
                candidates=[
                    RouteCandidate(provider="groq", model="llama-3.1-70b", context_window=128000, supports_json=True),
                    RouteCandidate(provider="together", model="qwen-2.5-72b", context_window=32768, supports_json=True),
                    RouteCandidate(provider="mistral", model="mistral-large", context_window=32768, supports_json=True),
                ],
                failure_prob=0.15,
                latency_ms=25.0,
                fail_kind=FailureKind.RATE_LIMITED,
            ),
            "ollama": ChaosFakeAdapter(
                name="ollama",
                candidates=[
                    RouteCandidate(provider="ollama", model="qwen3.5:latest", context_window=16384, supports_json=True),
                    RouteCandidate(provider="ollama", model="llama3.2:3b", context_window=8192, supports_json=True),
                ],
                failure_prob=0.02,
                latency_ms=10.0,
                fail_kind=FailureKind.SERVER_ERROR,
            ),
        }
        return adapters

    async def run_strategy(self, strategy: RoutingStrategy) -> StrategyMetricResult:
        random.seed(self.seed)
        adapters = self._setup_adapters()
        factory = StrategyRankerFactory()
        ranker = factory.get_ranker(strategy)

        router = PoolRouter(
            adapters=adapters,
            pools=POOLS,
            task_pool_map=TASK_POOL_MAP,
            ranker=ranker,
        )

        tasks = list(TaskType)
        latencies: list[float] = []
        successful = 0
        failed = 0
        fallbacks = 0
        context_overflows = 0

        for i in range(self.request_count):
            task = tasks[i % len(tasks)]
            req = LLMRequest(
                task=task,
                messages=[{"role": "user", "content": f"Test evaluation prompt {i}"}],
            )

            start = time.perf_counter()
            try:
                res = await router.complete(req)
                lat_ms = (time.perf_counter() - start) * 1000.0
                latencies.append(lat_ms)
                successful += 1

                # Record usage in ranker factory for stateful strategy ranking
                if res.provenance.served_by_provider and res.provenance.served_by_model:
                    factory.record_usage(
                        res.provenance.served_by_provider,
                        res.provenance.served_by_model,
                        lat_ms,
                    )

                if len(res.provenance.attempts) > 1:
                    fallbacks += len(res.provenance.attempts) - 1

            except LLMError as err:
                lat_ms = (time.perf_counter() - start) * 1000.0
                latencies.append(lat_ms)
                failed += 1
                # LLMError subclasses carry no .kind — the old `err.kind` check
                # raised AttributeError on the first all-routes-down request.
                if isinstance(err, ContextWindowExceeded):
                    context_overflows += 1

        latencies.sort()
        p50 = latencies[len(latencies) // 2] if latencies else 0.0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
        success_rate = (successful / self.request_count) * 100.0 if self.request_count > 0 else 0.0

        return StrategyMetricResult(
            strategy_name=strategy.value,
            total_requests=self.request_count,
            successful_requests=successful,
            failed_requests=failed,
            success_rate_pct=round(success_rate, 2),
            fallback_count=fallbacks,
            latency_p50_ms=round(p50, 2),
            latency_p95_ms=round(p95, 2),
            context_overflow_failures=context_overflows,
            # FakeAdapter tokens are len(text)//4 of a canned reply timed against
            # an injected sleep — not a throughput measurement, so: not measured.
            avg_tokens_per_sec=None,
        )

    async def run_all_strategies(self) -> list[StrategyMetricResult]:
        results: list[StrategyMetricResult] = []
        for strategy in RoutingStrategy:
            res = await self.run_strategy(strategy)
            results.append(res)
        return results
