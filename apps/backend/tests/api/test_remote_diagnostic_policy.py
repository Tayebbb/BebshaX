import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from bebshax.api.auth import get_current_user
from bebshax.api.openrouter_health import router
from bebshax.auth.models import Users
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.governance import RemoteProcessingPolicy, get_llm_request_context


@pytest.fixture
async def diagnostic_runtime(monkeypatch) -> AsyncIterator[tuple]:
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    calls = []
    records = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "catalog/diagnostic:free",
            "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
        })

    adapter = OpenRouterAdapter(
        api_key="synthetic-diagnostic-test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
        catalogue=[{
            "id": "catalog/diagnostic:free", "context_length": 131072,
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["response_format", "max_tokens", "temperature"],
        }],
    )
    app = FastAPI()
    app.include_router(router)

    async def authenticated_user() -> Users:
        return Users(id="usr_diagnostic", email="diagnostic@example.test", is_active=True, is_verified=True)

    app.dependency_overrides[get_current_user] = authenticated_user
    app.state.llm_adapters = {"openrouter": adapter}
    try:
        yield app, adapter, calls, records
    finally:
        service = getattr(app.state, "llm_service", None)
        if service is not None:
            await service.aclose()
        await adapter.aclose()


@pytest.mark.parametrize("approval", ["deny", "tier-only", "approved"])
async def test_fixed_diagnostic_uses_trusted_synthetic_context_and_explicit_upstream_policy(diagnostic_runtime, approval):
    app, adapter, calls, records = diagnostic_runtime
    policy = RemoteProcessingPolicy(
        policy_id="synthetic-diagnostic-fixture",
        synthetic_providers=frozenset({"openrouter"}) if approval != "deny" else frozenset(),
        synthetic_openrouter_upstreams=frozenset({"fixture-upstream"}) if approval == "approved" else frozenset(),
    )
    app.state.llm_service = SingleAdapterLLMService(adapter, processing_policy=policy, on_provenance=records.append)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/health/openrouter/test", json={"model": "catalog/diagnostic:free"})
    assert response.status_code == 200
    assert len(records) == 1
    assert records[0].owner_user_id == "usr_diagnostic"
    assert records[0].data_classification == "synthetic"
    assert records[0].task == "EMERGENCY_FALLBACK"
    if approval == "approved":
        assert response.json()["status"] == "available"
        assert calls[0]["provider"]["only"] == ["fixture-upstream"]
        assert calls[0]["messages"] == [{"role": "user", "content": 'Return exactly the JSON object {"ok":true}.'}]
    else:
        assert response.json()["status"] != "available"
        assert calls == []
    assert get_llm_request_context() is None


async def test_diagnostic_get_is_configuration_only_and_leaves_no_provenance(diagnostic_runtime):
    app, adapter, calls, records = diagnostic_runtime
    app.state.llm_service = SingleAdapterLLMService(adapter, on_provenance=records.append)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/openrouter")
    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert calls == []
    assert records == []