"""Unit tests for routing strategy rankers."""

from bebshax.evaluation.strategies import RoutingStrategy, StrategyRankerFactory
from bebshax.llm.adapters.base import RouteCandidate


def test_all_strategies_return_valid_rankings():
    candidates = [
        RouteCandidate(provider="p1", model="gpt-4o", context_window=128000, supports_json=True),
        RouteCandidate(provider="p2", model="qwen-2.5-72b", context_window=32768, supports_json=False),
        RouteCandidate(provider="p3", model="llama-3.2-3b", context_window=8192, supports_json=True),
    ]
    entries = [(None, c) for c in candidates]

    factory = StrategyRankerFactory()

    for strategy in RoutingStrategy:
        ranker = factory.get_ranker(strategy)
        ranked = ranker(entries)
        assert len(ranked) == len(entries)
        assert set(e[1].model for e in ranked) == set(c.model for c in candidates)


def test_round_robin_strategy_rotates():
    candidates = [
        RouteCandidate(provider="p1", model="m1"),
        RouteCandidate(provider="p2", model="m2"),
        RouteCandidate(provider="p3", model="m3"),
    ]
    entries = [(None, c) for c in candidates]

    factory = StrategyRankerFactory()
    rr_ranker = factory.get_ranker(RoutingStrategy.ROUND_ROBIN)

    r1 = rr_ranker(entries)
    assert r1[0][1].model == "m1"

    r2 = rr_ranker(entries)
    assert r2[0][1].model == "m2"

    r3 = rr_ranker(entries)
    assert r3[0][1].model == "m3"


def test_least_used_strategy():
    candidates = [
        RouteCandidate(provider="p1", model="m1"),
        RouteCandidate(provider="p2", model="m2"),
    ]
    entries = [(None, c) for c in candidates]

    factory = StrategyRankerFactory()
    # Record high usage for p1/m1
    factory.record_usage("p1", "m1", 100.0)
    factory.record_usage("p1", "m1", 100.0)

    ranker = factory.get_ranker(RoutingStrategy.LEAST_USED)
    ranked = ranker(entries)
    assert ranked[0][1].model == "m2"  # m2 used less
