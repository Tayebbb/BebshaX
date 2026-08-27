"""Unit tests for OfflineEvaluator."""

import json

from bebshax.evaluation.offline_evaluator import OfflineEvaluator


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
