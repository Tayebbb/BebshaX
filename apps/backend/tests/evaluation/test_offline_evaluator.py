"""Unit tests for OfflineEvaluator."""

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
