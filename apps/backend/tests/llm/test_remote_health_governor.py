import httpx
import pytest

from bebshax.llm import SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.openrouter_service import OpenRouterService


def configured_adapter(calls):
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    return OpenRouterAdapter(
        api_key="synthetic-test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        catalogue=[{
            "id": "catalog/diagnostic:free", "context_length": 128000,
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["response_format", "max_tokens", "temperature"],
        }],
    )


class Governor(SingleAdapterLLMService):
    def __init__(self, reply='{"ok":true}', provider="openrouter"):
        self.records = []
        self.requests = []
        super().__init__(FakeAdapter([FakeRoute(candidate=RouteCandidate(provider=provider, model="reported-model"), reply=reply)]), on_provenance=self.records.append)

    async def complete(self, request):
        self.requests.append(request)
        return await super().complete(request)


@pytest.fixture(autouse=True)
def clear_pins(monkeypatch):
    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)


async def test_diagnostic_uses_injected_governor_and_explicit_task_with_provenance():
    direct_calls = []
    adapter = configured_adapter(direct_calls)
    governor = Governor()
    try:
        result = await OpenRouterService(adapter).health_check(llm_service=governor, model="catalog/diagnostic:free")
        assert result["status"] == "healthy"
        assert result["model"] == "reported-model"
        assert result["request_id"] == governor.records[0].request_id
        assert governor.requests[0].task == TaskType.EMERGENCY_FALLBACK
        assert governor.requests[0].json_mode is True
        assert not direct_calls
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("service_path", [True, False])
async def test_no_governor_is_an_explicit_error_not_a_direct_completion_fallback(service_path):
    direct_calls = []
    adapter = configured_adapter(direct_calls)
    target = OpenRouterService(adapter) if service_path else adapter
    try:
        with pytest.raises(TypeError, match="llm_service"):
            await target.health_check(model="catalog/diagnostic:free")
        assert not direct_calls
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("reply", ["", "{}", '{"ok":false}'])
async def test_empty_or_invalid_diagnostic_is_not_healthy(reply):
    adapter = configured_adapter([])
    try:
        result = await OpenRouterService(adapter).health_check(llm_service=Governor(reply), model="catalog/diagnostic:free")
        assert result["status"] != "healthy"
    finally:
        await adapter.aclose()


async def test_another_serving_provider_does_not_verify_openrouter_authentication():
    adapter = configured_adapter([])
    try:
        result = await OpenRouterService(adapter).health_check(llm_service=Governor(provider="primary"), model="catalog/diagnostic:free")
        assert result["status"] == "unverified"
        assert result["authenticated"] is False
        assert result["provider"] == "primary"
    finally:
        await adapter.aclose()


async def test_paid_diagnostic_model_is_denied_before_governor_call():
    adapter = configured_adapter([])
    governor = Governor()
    try:
        result = await OpenRouterService(adapter).health_check(llm_service=governor, model="catalog/paid")
        assert result["status"] == "error"
        assert governor.requests == []
    finally:
        await adapter.aclose()