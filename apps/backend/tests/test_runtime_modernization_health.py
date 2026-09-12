from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bebshax.api import health, openrouter_health
from bebshax.api.auth import get_current_user
from bebshax.api.errors import register_exception_handlers
from bebshax.api.limiter import limiter
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.llm.types import TaskType


class DiagnosticAdapter:
    streaming_mode = "native"

    def __init__(self):
        self.candidates = AsyncMock(return_value=[RouteCandidate(
            provider="openrouter", model="test/verified:free", context_window=10000,
        )])

    def configuration_status(self, model=None):
        return {"configured": True, "authenticated": False, "model": model or "test/verified:free",
                "models": ["test/verified:free"], "status": "configured", "message": "Configured, not verified."}

    def catalogue_status(self):
        return {"pinned": [], "discovered": ["test/verified:free"], "fetched_at": 1, "error": None,
                "discovery_enabled": True}


def _app():
    app = FastAPI()
    register_exception_handlers(app)
    app.state.limiter = limiter
    app.include_router(health.router, prefix="/api")
    app.include_router(openrouter_health.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="runtime-test-user")
    app.state.llm_adapters = {"openrouter": DiagnosticAdapter()}
    app.state.llm_service = SimpleNamespace(complete=AsyncMock())
    app.state.provider_health = {}
    return app


async def test_openrouter_get_uses_only_shared_configuration():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/openrouter")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["authenticated"] is False
    assert body["status"] == "configured"
    assert body["models"] == ["test/verified:free"]
    assert body["streaming_mode"] == "native"
    app.state.llm_adapters["openrouter"].candidates.assert_not_awaited()
    app.state.llm_service.complete.assert_not_awaited()


async def test_unwired_openrouter_get_is_unknown_not_a_new_singleton():
    app = _app()
    app.state.llm_adapters = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/health/openrouter")).json()
    assert body["status"] == "unknown"
    assert body["error_code"] == "RUNTIME_NOT_READY"


@pytest.mark.parametrize("provider,expected_status", [("openrouter", "available"), ("groq", "unknown")])
async def test_diagnostic_post_is_governed_and_keeps_serving_identity(provider, expected_status):
    app = _app()
    record = ProvenanceRecord(request_id="governed-diagnostic", task="EMERGENCY_FALLBACK", success=True)
    app.state.llm_service.complete.return_value = SimpleNamespace(
        provider=provider, model="test/verified:free", text='{"ok":true}', provenance=record,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/health/openrouter/test", json={"model": "test/verified:free"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == provider
    assert body["request_id"] == record.request_id
    assert body["status"] == expected_status
    assert body["authenticated"] is (provider == "openrouter")
    request = app.state.llm_service.complete.call_args.args[0]
    assert request.task == TaskType.EMERGENCY_FALLBACK
    assert request.json_mode is True


async def test_core_readiness_requires_startup_validation_not_only_select_one(monkeypatch):
    app = _app()
    monkeypatch.setattr(health, "probe_database", AsyncMock(return_value="ok"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json()["error_code"] == "runtime_not_ready"


async def test_optional_ml_failure_does_not_dead_end_core_chat(monkeypatch):
    app = _app()
    app.state.core_ready = True
    app.state.database_revision_validated = True
    app.state.persona_required = False
    app.state.persona_capability = {"status": "unavailable", "reason": "artifact_unavailable"}
    monkeypatch.setattr(health, "probe_database", AsyncMock(return_value="ok"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        live = (await client.get("/api/health")).json()
        ready = await client.get("/api/health/ready")
    assert ready.status_code == 200
    assert live["core_ready"] is True
    assert live["capabilities"]["persona_generation"]["status"] == "unavailable"
    assert live["providers"][0]["status"] == "configured"
    assert "local_tier_up" not in live
    app.state.llm_adapters["openrouter"].candidates.assert_not_awaited()
    app.state.llm_service.complete.assert_not_awaited()


def test_provider_availability_needs_recent_non_cached_success():
    app = _app()
    assert health.provider_status_snapshot(app)[0]["status"] == "configured"
    now = datetime.now(timezone.utc)
    record = ProvenanceRecord(request_id="observed", task="PERSONA_RESPONSE", success=True,
                              attempts=[AttemptRecord(attempt_number=1, provider="openrouter",
                                                      model="test", success=True, started_at=now)])
    health.record_provider_observations(app, record)
    assert health.provider_status_snapshot(app)[0]["status"] == "available"
    record.attempts[0].started_at = now - timedelta(hours=1)
    app.state.provider_health = {}
    health.record_provider_observations(app, record)
    assert health.provider_status_snapshot(app)[0]["status"] == "configured"
    record.attempts[0].started_at = now
    record.attempts[0].cached = True
    app.state.provider_health = {}
    health.record_provider_observations(app, record)
    assert health.provider_status_snapshot(app)[0]["status"] == "configured"


async def test_diagnostic_model_input_is_bounded():
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/health/openrouter/test", json={"model": "x" * 257})
    assert response.status_code == 422


async def test_governed_diagnostic_binds_authenticated_owner():
    from bebshax.tenancy_context import get_tenant_owner_id

    app = _app()
    owners = []

    async def complete(request):
        owners.append(get_tenant_owner_id())
        return SimpleNamespace(provider="openrouter", model="test/verified:free", text='{"ok":true}',
                               provenance=ProvenanceRecord(request_id="owned-check", task="EMERGENCY_FALLBACK", success=True))

    app.state.llm_service.complete.side_effect = complete
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/health/openrouter/test", json={"model": "test/verified:free"})
    assert response.status_code == 200
    assert owners == ["runtime-test-user"]