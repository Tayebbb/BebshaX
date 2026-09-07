"""Unit tests for OfflineEvaluator."""

import json

from bebshax.evaluation.offline_evaluator import OfflineEvaluator
from bebshax.evaluation.strategies import RoutingStrategy


def test_offline_evaluator_router_arena():
    evaluator = OfflineEvaluator()
    res = evaluator.evaluate_router_arena()

    assert res.dataset_name == "router_arena"
    assert res.total_samples > 0
    assert "HYBRID" in res.strategy_scores
    assert "ROUND_ROBIN" in res.strategy_scores


def test_offline_evaluator_xroute_bench():
    evaluator = OfflineEvaluator()
    res = evaluator.evaluate_xroute_bench()

    assert res.dataset_name == "xroute_bench"
    assert res.total_samples > 0
    assert "QUALITY_FIRST" in res.strategy_scores
    assert "LATENCY_FIRST" in res.strategy_scores


def test_absent_datasets_are_flagged_as_synthetic_fallback(tmp_path):
    """Synthetic replays must never masquerade as benchmark results."""
    evaluator = OfflineEvaluator(data_dir=tmp_path)  # no dataset files
    ra = evaluator.evaluate_router_arena()
    xb = evaluator.evaluate_xroute_bench()
    assert ra.synthetic_fallback is True
    assert xb.synthetic_fallback is True


def test_real_datasets_are_not_flagged(tmp_path):
    (tmp_path / "router_arena.jsonl").write_text(
        json.dumps(
            {"id": "r1", "prompt": "q", "domain": "reasoning",
             "model_scores": {"llama-3.1-70b": 0.9, "qwen-2.5-72b": 0.7}}
        ),
        encoding="utf-8",
    )
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_router_arena()
    assert res.synthetic_fallback is False
    assert res.total_samples == 1
    assert res.usable_samples == 1 and res.unusable is False and res.unusable_reason is None
    assert res.strategy_scores["HYBRID"] == 1.0  # HYBRID keeps pool order → llama-3.1-70b first


def test_records_without_model_scores_are_unusable_and_never_default_to_a_winner(tmp_path):
    """The pinned RouterArena slice has no per-model labels. The old evaluator
    defaulted best_model to 'llama-3.1-70b' — the HYBRID ranker's first pick —
    and reported a 100% alignment tautology. Now: unusable, alignment None."""
    (tmp_path / "router_arena.jsonl").write_text(
        "\n".join(
            json.dumps({"id": f"r{i}", "prompt": f"q{i}", "domain": "misc", "model_scores": {}})
            for i in range(3)
        ),
        encoding="utf-8",
    )
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_router_arena()
    assert res.synthetic_fallback is False
    assert res.total_samples == 3 and res.usable_samples == 0 and res.unusable_samples == 3
    assert res.unusable is True and "no model_scores" in (res.unusable_reason or "")
    assert set(res.strategy_scores) == {s.value for s in RoutingStrategy}
    assert all(score is None for score in res.strategy_scores.values())


def test_alignment_is_computed_over_usable_records_only(tmp_path):
    rows = [
        {"id": "a", "prompt": "q", "domain": "d", "model_scores": {"qwen-2.5-72b": 0.9, "llama-3.1-70b": 0.1}},
        {"id": "b", "prompt": "q", "domain": "d", "model_scores": {}},  # unusable, must not dilute
    ]
    (tmp_path / "router_arena.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_router_arena()
    assert res.usable_samples == 1 and res.unusable_samples == 1 and res.unusable is False
    assert res.unusable_reason is not None  # partial unusability is still reported
    assert res.strategy_scores["HYBRID"] == 0.0  # HYBRID picks llama-3.1-70b; label says qwen


def test_xroute_records_without_candidates_are_unusable(tmp_path):
    """Real xRouteBench rows carry query/task/metadata but no candidate executions;
    the old default 'qwen3.5:latest' matched the first candidate route by construction."""
    (tmp_path / "xroute_bench.jsonl").write_text(
        json.dumps({"id": "x1", "query": "Q", "task": "mmlu", "metadata": {"metric": "em_mc"}}),
        encoding="utf-8",
    )
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_xroute_bench()
    assert res.unusable is True and res.usable_samples == 0
    assert "no ranked candidates" in (res.unusable_reason or "")
    assert all(score is None for score in res.strategy_scores.values())


def test_xroute_scored_candidates_pick_the_highest_score_not_the_first(tmp_path):
    (tmp_path / "xroute_bench.jsonl").write_text(
        json.dumps({
            "id": "x1", "query": "Q", "task": "general",
            "candidates": [{"model": "qwen3.5:latest", "score": 0.4}, {"model": "llama-3.1-70b", "score": 0.9}],
        }),
        encoding="utf-8",
    )
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_xroute_bench()
    assert res.usable_samples == 1
    assert res.strategy_scores["HYBRID"] == 0.0  # HYBRID picks the first route (qwen); label is llama
    assert res.strategy_scores["CAPABILITY_FIRST"] == 1.0  # largest window → llama-3.1-70b


def test_synthetic_fallback_records_are_usable_but_flagged(tmp_path):
    res = OfflineEvaluator(data_dir=tmp_path).evaluate_router_arena()
    assert res.synthetic_fallback is True and res.unusable is False
    assert res.usable_samples == res.total_samples == 50
