from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from bebshax.api.routes import get_routes_status
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


class ConfiguredAdapter(FakeAdapter):
    def configuration_status(self) -> dict[str, bool]:
        return {"configured": True}


def status_request(
    *, provider: str = "openrouter", models: tuple[str, ...] = ("verified-model",),
    cooling: tuple[str, ...] = (), observed: bool | None = None, stale: bool = False,
    configured: bool = True,
) -> tuple[Request, FakeAdapter]:
    adapter_type = ConfiguredAdapter if configured else FakeAdapter
    adapter = adapter_type([
        FakeRoute(RouteCandidate(provider=provider, model=model, context_window=131072))
        for model in models
    ])
    observations = {}
    if observed is not None:
        observations[provider] = {
            "observed_at": datetime.now(timezone.utc) - timedelta(seconds=600 if stale else 1),
            "success": observed,
        }
    state = SimpleNamespace(
        llm_adapters={provider: adapter},
        llm_router=SimpleNamespace(is_cooling=lambda candidate: candidate.model in cooling),
        provider_health=observations,
    )
    return Request({"type": "http", "method": "GET", "app": SimpleNamespace(state=state)}), adapter


async def test_catalog_candidates_are_configured_not_a_successful_health_probe() -> None:
    request, adapter = status_request()
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == "configured"
    assert provider["recent_success"] is False
    assert provider["candidate_count"] == 1
    assert adapter.calls == []


@pytest.mark.parametrize("success, expected", [(True, "available"), (False, "degraded")])
async def test_route_status_uses_recent_runtime_observations(success: bool, expected: str) -> None:
    request, adapter = status_request(observed=success)
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == expected
    assert provider["recent_success"] is success
    assert adapter.calls == []


async def test_stale_success_does_not_claim_current_provider_health() -> None:
    request, _adapter = status_request(observed=True, stale=True)
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == "configured"
    assert provider["recent_success"] is False


async def test_all_cooling_candidates_are_unavailable_even_after_recent_success() -> None:
    request, adapter = status_request(
        models=("first", "second"), cooling=("first", "second"), observed=True,
    )
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == "unavailable"
    assert provider["available_models"] == 0
    assert provider["candidate_count"] == 2
    assert provider["active_cooldowns"] == 2
    assert provider["recent_success"] is True
    assert adapter.calls == []


async def test_virtual_primary_is_not_an_observed_healthy_model_fleet() -> None:
    request, adapter = status_request(provider="freellmpool", models=("auto",), configured=False)
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == "unknown"
    assert provider["available_models"] is None
    assert provider["candidate_count"] == 1
    assert adapter.calls == []


async def test_missing_cooldown_state_does_not_invent_an_available_model_count() -> None:
    request, _adapter = status_request()
    request.app.state.llm_router = None
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["active_cooldowns"] is None
    assert provider["available_models"] is None


async def test_legacy_ollama_identifier_does_not_prove_local_route_kind() -> None:
    request, _adapter = status_request(provider="ollama", models=(), configured=False)
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["type"] == "unknown"
    assert provider["status"] != "healthy"


async def test_discovery_failure_is_unavailable_and_does_not_log_provider_details(monkeypatch, caplog) -> None:
    request, adapter = status_request(observed=True)

    async def fail_discovery() -> list[RouteCandidate]:
        raise RuntimeError("synthetic-private-discovery-sentinel")

    monkeypatch.setattr(adapter, "candidates", fail_discovery)
    [provider] = (await get_routes_status(request))["providers"]
    assert provider["status"] == "unavailable"
    assert provider["available_models"] == 0
    assert "synthetic-private-discovery-sentinel" not in caplog.text
    assert adapter.calls == []