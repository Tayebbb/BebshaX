"""Unit tests for RoutingChaosSimulator."""

import pytest
from bebshax.evaluation.routing_simulator import RoutingChaosSimulator
from bebshax.evaluation.strategies import RoutingStrategy


@pytest.mark.asyncio
async def test_run_single_strategy_simulation():
    simulator = RoutingChaosSimulator(request_count=10, seed=123)
    res = await simulator.run_strategy(RoutingStrategy.HYBRID)

    assert res.strategy_name == "HYBRID"
    assert res.total_requests == 10
    assert res.successful_requests + res.failed_requests == 10
    assert 0.0 <= res.success_rate_pct <= 100.0


@pytest.mark.asyncio
async def test_simulation_is_labelled_control_flow_and_reports_no_fake_throughput():
    """avg_tokens_per_sec used to be a hardcoded 120.5 written into every artifact."""
    res = await RoutingChaosSimulator(request_count=5, seed=1).run_strategy(RoutingStrategy.HYBRID)
    assert res.kind == "router_control_flow_simulation"
    assert res.avg_tokens_per_sec is None
    assert res.model_dump()["avg_tokens_per_sec"] is None


@pytest.mark.asyncio
async def test_run_all_strategies_simulation():
    simulator = RoutingChaosSimulator(request_count=10, seed=456)
    results = await simulator.run_all_strategies()

    assert len(results) == len(RoutingStrategy)
    strat_names = [r.strategy_name for r in results]
    assert "ROUND_ROBIN" in strat_names
    assert "QUALITY_FIRST" in strat_names
    assert "LEAST_USED" in strat_names
