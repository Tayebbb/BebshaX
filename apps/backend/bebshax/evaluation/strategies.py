"""Pluggable routing strategy rankers for PoolRouter.

Supported strategies:
- HYBRID (Default): Preserves pool order.
- ROUND_ROBIN: Rotates candidates round-robin.
- LEAST_USED: Ranks candidates by lowest total execution count.
- QUALITY_FIRST: Ranks candidates by higher estimated model quality.
- LATENCY_FIRST: Ranks candidates by lower estimated latency.
- CAPABILITY_FIRST: Ranks candidates by context window size and capabilities.
- QUOTA_AWARE: Ranks candidates by cooling status and provider capacity.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable

from bebshax.llm.service import Entry


class RoutingStrategy(str, Enum):
    HYBRID = "HYBRID"
    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_USED = "LEAST_USED"
    QUALITY_FIRST = "QUALITY_FIRST"
    LATENCY_FIRST = "LATENCY_FIRST"
    CAPABILITY_FIRST = "CAPABILITY_FIRST"
    QUOTA_AWARE = "QUOTA_AWARE"


class StrategyRankerFactory:
    """Stateful factory holding rankers for routing strategy experiments."""

    def __init__(self) -> None:
        self._rr_index: int = 0
        self._usage_counts: dict[tuple[str, str], int] = {}
        self._latency_history: dict[tuple[str, str], float] = {}

    def record_usage(self, provider: str, model: str, latency_ms: float = 0.0) -> None:
        key = (provider, model)
        self._usage_counts[key] = self._usage_counts.get(key, 0) + 1
        if latency_ms > 0:
            prev = self._latency_history.get(key, latency_ms)
            self._latency_history[key] = 0.7 * prev + 0.3 * latency_ms

    def get_ranker(self, strategy: RoutingStrategy | str) -> Callable[[list[Entry]], list[Entry]]:
        strat = RoutingStrategy(strategy) if isinstance(strategy, str) else strategy

        if strat == RoutingStrategy.HYBRID:
            return self._rank_hybrid
        elif strat == RoutingStrategy.ROUND_ROBIN:
            return self._rank_round_robin
        elif strat == RoutingStrategy.LEAST_USED:
            return self._rank_least_used
        elif strat == RoutingStrategy.QUALITY_FIRST:
            return self._rank_quality_first
        elif strat == RoutingStrategy.LATENCY_FIRST:
            return self._rank_latency_first
        elif strat == RoutingStrategy.CAPABILITY_FIRST:
            return self._rank_capability_first
        elif strat == RoutingStrategy.QUOTA_AWARE:
            return self._rank_quota_aware
        else:
            return self._rank_hybrid

    def _rank_hybrid(self, entries: list[Entry]) -> list[Entry]:
        return list(entries)

    def _rank_round_robin(self, entries: list[Entry]) -> list[Entry]:
        if not entries:
            return entries
        n = len(entries)
        idx = self._rr_index % n
        self._rr_index += 1
        return entries[idx:] + entries[:idx]

    def _rank_least_used(self, entries: list[Entry]) -> list[Entry]:
        return sorted(
            entries,
            key=lambda e: self._usage_counts.get((e[1].provider, e[1].model), 0),
        )

    def _rank_quality_first(self, entries: list[Entry]) -> list[Entry]:
        def quality_score(entry: Entry) -> float:
            model = entry[1].model.lower()
            if "claude" in model or "gpt-4" in model or "gemini-1.5-pro" in model:
                return 100.0
            if "qwen" in model or "llama-3" in model or "deepseek" in model:
                return 80.0
            return 60.0

        return sorted(entries, key=quality_score, reverse=True)

    def _rank_latency_first(self, entries: list[Entry]) -> list[Entry]:
        return sorted(
            entries,
            key=lambda e: self._latency_history.get((e[1].provider, e[1].model), 100.0),
        )

    def _rank_capability_first(self, entries: list[Entry]) -> list[Entry]:
        def capability_score(entry: Entry) -> tuple[int, int]:
            cand = entry[1]
            return (cand.context_window, 1 if cand.supports_json else 0)

        return sorted(entries, key=capability_score, reverse=True)

    def _rank_quota_aware(self, entries: list[Entry]) -> list[Entry]:
        # Prefer candidates with lower cumulative usage count
        return sorted(
            entries,
            key=lambda e: (
                self._usage_counts.get((e[1].provider, e[1].model), 0),
                -e[1].context_window,
            ),
        )
