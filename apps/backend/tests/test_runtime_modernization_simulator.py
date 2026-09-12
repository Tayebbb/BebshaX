from bebshax.evaluation.offline_evaluator import OfflineEvaluator
from bebshax.evaluation.routing_simulator import RoutingChaosSimulator
from bebshax.evaluation.strategies import RoutingStrategy


def test_chaos_simulator_uses_two_remote_tiers_with_real_secondary_slot():
    adapters = RoutingChaosSimulator()._setup_adapters()
    assert set(adapters) == {"freellmpool", "openrouter"}
    assert adapters["openrouter"]._routes
    assert all(provider != "ollama" for adapter in adapters.values() for provider, _ in adapter._routes)


async def test_total_remote_outage_has_no_offline_success(monkeypatch):
    simulator = RoutingChaosSimulator(request_count=4)
    adapters = simulator._setup_adapters()
    for adapter in adapters.values():
        adapter.failure_prob = 1.0
        adapter.latency_ms = 0
    monkeypatch.setattr(simulator, "_setup_adapters", lambda: adapters)
    result = await simulator.run_strategy(next(iter(RoutingStrategy)))
    assert result.total_requests == 4
    assert result.successful_requests == 0
    assert result.failed_requests == 4
    assert result.success_rate_pct == 0


def test_offline_synthetic_candidates_do_not_revive_local_routes(monkeypatch, tmp_path):
    from bebshax.evaluation import offline_evaluator

    captured = []
    original = offline_evaluator._replay

    def replay(dataset, records, candidates, *args):
        captured.extend(candidates)
        return original(dataset, records, candidates, *args)

    monkeypatch.setattr(offline_evaluator, "_replay", replay)
    result = OfflineEvaluator(tmp_path).evaluate_xroute_bench()
    assert result.synthetic_fallback is True
    assert {candidate.provider for candidate in captured} == {"groq", "openrouter"}