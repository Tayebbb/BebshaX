import pytest

from bebshax.api.demo_lab import SCENARIOS, _lab
from bebshax.llm.failures import FailureKind


@pytest.mark.parametrize("name", tuple(SCENARIOS))
async def test_remote_simulations_match_advertised_outcome(name):
    spec = SCENARIOS[name]
    result = await spec.builder()
    assert result.outcome == spec.expected_outcome
    assert set(_lab().adapters) == {"freellmpool", "openrouter"}
    assert all(attempt.provider != "ollama" for attempt in result.provenance.attempts)


async def test_total_remote_outage_retains_failures_and_retry():
    result = await SCENARIOS["all_providers_down"].builder()
    assert result.error_code == "all_candidates_failed"
    assert not result.provenance.success
    assert result.provenance.served_by_provider is None
    assert [attempt.failure_kind for attempt in result.provenance.attempts] == [
        FailureKind.RATE_LIMITED,
        FailureKind.QUOTA_EXHAUSTED,
        FailureKind.CONNECTION,
        FailureKind.CONNECTION,
    ]
    assert result.provenance.attempts[2].fallback_reason == "retrying same route once"