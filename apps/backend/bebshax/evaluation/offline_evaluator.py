"""Offline dataset replay evaluator for routing strategy benchmarks.

Honesty contract: a record is only *usable* when it carries per-model labels
(``model_scores`` for RouterArena, ranked ``candidates`` for xRouteBench).
Records without labels are counted as unusable with a reason and contribute
NOTHING — the evaluator never invents a "best model" to match against, so a
dataset without labels yields ``None`` alignment, never a 100% tautology.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from bebshax.evaluation.strategies import RoutingStrategy, StrategyRankerFactory
from bebshax.evaluation.types import OfflineEvalResult
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.llm.service import Entry

DATA_DIR = Path("data/processed")

ROUTER_ARENA_NO_SCORES = (
    "record carries no model_scores — the pinned RouterArena sub_10 slice has no "
    "per-model labels, so no 'best model' exists to align with"
)
XROUTE_NO_CANDIDATES = (
    "record carries no ranked candidates — the pinned xRouteBench slice has no "
    "per-model executions, so no 'best model' exists to align with"
)


def _read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
    return records


def _router_arena_best(rec: dict[str, Any]) -> str | None:
    scores = rec.get("model_scores")
    if not isinstance(scores, dict) or not scores:
        return None
    numeric = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
    if not numeric:
        return None
    return max(numeric, key=lambda k: numeric[k])


def _xroute_best(rec: dict[str, Any]) -> str | None:
    cand_list = rec.get("candidates")
    if not isinstance(cand_list, list) or not cand_list:
        return None
    ranked = [c for c in cand_list if isinstance(c, dict) and c.get("model")]
    if not ranked:
        return None
    scored = [c for c in ranked if isinstance(c.get("score"), (int, float))]
    if scored:
        return max(scored, key=lambda c: c["score"])["model"]
    return ranked[0]["model"]


def _replay(
    dataset_name: str,
    records: list[dict[str, Any]],
    candidates: list[RouteCandidate],
    best_of: Callable[[dict[str, Any]], str | None],
    unusable_reason: str,
    synthetic_fallback: bool,
) -> OfflineEvalResult:
    offline_adapter = FakeAdapter([])
    entries: list[Entry] = [(offline_adapter, candidate) for candidate in candidates]
    usable = [(rec, best) for rec in records if (best := best_of(rec)) is not None]
    unusable_count = len(records) - len(usable)

    scores: dict[str, float | None] = {}
    factory = StrategyRankerFactory()
    for strategy in RoutingStrategy:
        ranker = factory.get_ranker(strategy)
        if not usable:
            scores[strategy.value] = None  # nothing to align with — never a default winner
            continue
        matched = sum(1 for _rec, best in usable if ranker(list(entries))[0][1].model == best)
        scores[strategy.value] = round(matched / len(usable), 4)

    return OfflineEvalResult(
        dataset_name=dataset_name,
        total_samples=len(records),
        usable_samples=len(usable),
        unusable_samples=unusable_count,
        unusable=not usable,
        unusable_reason=unusable_reason if unusable_count else None,
        strategy_scores=scores,
        synthetic_fallback=synthetic_fallback,
    )


class OfflineEvaluator:
    """Evaluates routing strategies against offline datasets without network calls."""

    def __init__(self, data_dir: Path | str = DATA_DIR) -> None:
        self.data_dir = Path(data_dir)

    def evaluate_router_arena(self) -> OfflineEvalResult:
        records = _read_jsonl(self.data_dir / "router_arena.jsonl")
        synthetic_fallback = not records
        if synthetic_fallback:
            # Fallback synthetic records — flagged in the result so reports
            # never present them as real benchmark measurements.
            records = [
                {
                    "id": f"ra-{i}",
                    "prompt": f"Domain query prompt {i}",
                    "domain": "coding" if i % 2 == 0 else "reasoning",
                    "model_scores": {"llama-3.1-70b": 0.9, "qwen-2.5-72b": 0.85, "mistral-large": 0.8},
                }
                for i in range(50)
            ]

        candidates = [
            RouteCandidate(provider="groq", model="llama-3.1-70b", context_window=128000),
            RouteCandidate(provider="together", model="qwen-2.5-72b", context_window=32768),
            RouteCandidate(provider="mistral", model="mistral-large", context_window=32768),
        ]
        return _replay(
            "router_arena", records, candidates, _router_arena_best, ROUTER_ARENA_NO_SCORES, synthetic_fallback
        )

    def evaluate_xroute_bench(self) -> OfflineEvalResult:
        records = _read_jsonl(self.data_dir / "xroute_bench.jsonl")
        synthetic_fallback = not records
        if synthetic_fallback:
            records = [
                {
                    "id": f"xb-{i}",
                    "query": f"Benchmark query {i}",
                    "task": "structured" if i % 3 == 0 else "general",
                    "candidates": [
                        {"model": "simulation/secondary:free", "score": 0.92},
                        {"model": "llama-3.1-70b", "score": 0.88},
                    ],
                }
                for i in range(50)
            ]

        candidates = [
            RouteCandidate(provider="openrouter", model="simulation/secondary:free", context_window=32768),
            RouteCandidate(provider="groq", model="llama-3.1-70b", context_window=128000),
        ]
        return _replay(
            "xroute_bench", records, candidates, _xroute_best, XROUTE_NO_CANDIDATES, synthetic_fallback
        )
