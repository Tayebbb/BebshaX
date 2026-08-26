"""Tests for OpenRouter health verification and central diagnostic service."""

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from bebshax.llm import AttemptFailed, ChatMessage, FailureKind, LLMRequest, TaskType
from bebshax.llm.adapters.base import RouteCandidate
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
async def test_openrouter_truncated_output_is_malformed_response(monkeypatch):
    """finish_reason=length ⇒ MALFORMED_RESPONSE (retry-once-then-advance)."""
    adapter = OpenRouterAdapter(api_key="test-key-not-real")

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "We need to respond as the persona. The researc"},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 450},
                "model": "some/reasoning-model:free",
            },
        )

    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    candidate = RouteCandidate(
        provider="openrouter",
        model="some/reasoning-model:free",
        context_window=8192,
        supports_json=True,
        supports_tools=False,
    )
    req = LLMRequest(
        task=TaskType.PERSONA_INTERVIEW,
        messages=[ChatMessage(role="user", content="hello")],
        max_output_tokens=450,
    )
    with pytest.raises(AttemptFailed) as exc:
        await adapter.complete(candidate, req)
    assert exc.value.kind == FailureKind.MALFORMED_RESPONSE
    assert "truncated" in exc.value.detail.lower()


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
