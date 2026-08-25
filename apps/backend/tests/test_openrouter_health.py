"""Tests for OpenRouter health verification and central diagnostic service."""

import pytest
from httpx import ASGITransport, AsyncClient

from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.openrouter_service import OpenRouterService
from bebshax.main import app


@pytest.mark.asyncio
async def test_openrouter_health_not_configured(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    adapter = OpenRouterAdapter(api_key="")
    result = await adapter.health_check()
    assert result["configured"] is False
    assert result["authenticated"] is False
    assert result["status"] == "not_configured"
    assert result["error_code"] == "OPENROUTER_NOT_CONFIGURED"
    # Never leak any secret
    assert "api_key" not in result
    assert "Authorization" not in str(result)


@pytest.mark.asyncio
async def test_openrouter_service_role_models(monkeypatch):
    monkeypatch.setenv("MODEL_PERSONA", "meta-llama/llama-3.3-70b-instruct:free")
    monkeypatch.setenv("MODEL_REASONING", "deepseek/deepseek-r1:free")
    service = OpenRouterService()
    assert service.get_model_for_role("persona") == "meta-llama/llama-3.3-70b-instruct:free"
    assert service.get_model_for_role("reasoning") == "deepseek/deepseek-r1:free"


@pytest.mark.asyncio
async def test_openrouter_health_api_endpoint(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health/openrouter")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "authenticated" in data
        assert "status" in data
        assert "api_key" not in data
        assert "Authorization" not in str(data)
