"""GET /api/health/openrouter is a configuration report — no network, no spend.

Regression: the anonymous, unlimited GET performed a REAL OpenRouter
completion on every call (a free-tier budget drain anyone could trigger); the
authenticated, rate-limited POST /test is the only path that probes live.
"""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from bebshax.llm.adapters.openrouter_adapter import DEFAULT_MODELS, OpenRouterAdapter
from bebshax.llm.openrouter_service import OpenRouterService
from bebshax.main import app


@pytest.fixture
def _no_network(monkeypatch):
    """Any outbound httpx request that is not the in-process ASGI test client
    fails the test (the test client itself is an httpx.AsyncClient)."""
    original_send = httpx.AsyncClient.send

    async def _guarded_send(self, request, *args, **kwargs):
        if request.url.host != "test":
            raise AssertionError(
                f"GET /api/health/openrouter must not perform network I/O (saw {request.url})"
            )
        return await original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", _guarded_send)


async def test_get_reports_configured_key_without_network(monkeypatch, _no_network) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-real")
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("MODEL_REASONING", raising=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health/openrouter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["authenticated"] is False  # not verified — only POST /test verifies
    assert data["status"] == "configured"
    assert data["models"] == DEFAULT_MODELS
    assert data["latency_ms"] is None and data["verified_response"] is None
    assert "sk-or" not in str(data)  # never echoes the key


async def test_get_reports_missing_key_without_network(monkeypatch, _no_network) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health/openrouter")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["status"] == "not_configured"
    assert data["error_code"] == "OPENROUTER_NOT_CONFIGURED"
    assert data["models"] == []


def test_configuration_report_honours_model_override(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-not-real")
    monkeypatch.setenv("BEBSHAX_OPENROUTER_MODELS", "a/b:free, c/d:free")
    report = OpenRouterService(OpenRouterAdapter()).configuration_report()
    assert report["models"] == ["a/b:free", "c/d:free"]
    assert report["configured"] is True


async def test_post_test_requires_auth_and_is_rate_limited() -> None:
    """The live probe keeps its auth + limiter posture."""
    from bebshax.api.auth import get_current_user
    from bebshax.api.limiter import limiter
    from bebshax.api.openrouter_health import router as health_router

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/health/openrouter/test", json={})
    assert resp.status_code in (401, 403)

    [route] = [r for r in health_router.routes if r.path == "/health/openrouter/test"]
    assert get_current_user in {d.call for d in route.dependant.dependencies}
    registered = {k for k in limiter._route_limits if k.endswith("test_openrouter_connection")}
    assert registered, "POST /test lost its slowapi limit"
    assert all(
        str(lim.limit) == "10 per 1 hour" for key in registered for lim in limiter._route_limits[key]
    )


def test_service_no_longer_offers_a_completion_bypass() -> None:
    """Every completion goes through LLMService (R3): the R3-bypassing
    generate_structured helper had zero callers and is gone."""
    assert not hasattr(OpenRouterService, "generate_structured")
