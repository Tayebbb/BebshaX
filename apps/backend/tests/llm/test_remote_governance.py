import asyncio
import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, PoolRouter, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import AllCandidatesFailed


class RemoteFakeAdapter(FakeAdapter):
    remote_processing = True


def remote_adapter() -> RemoteFakeAdapter:
    return RemoteFakeAdapter([
        FakeRoute(candidate=RouteCandidate(provider="freellmpool", model="verified-model"), reply="Complete answer"),
    ])


def request(**changes) -> LLMRequest:
    return LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[ChatMessage(role="user", content="Full private research context")],
        **changes,
    )


@pytest.mark.parametrize("service_kind", ["single", "pool", "stream"])
async def test_caller_self_attestation_without_server_context_cannot_authorize_remote_dispatch(service_kind: str) -> None:
    adapter = remote_adapter()
    records = []
    service = (
        SingleAdapterLLMService(adapter, on_provenance=records.append)
        if service_kind == "single"
        else PoolRouter({"freellmpool": adapter, "openrouter": FakeAdapter([])}, on_provenance=records.append)
    )
    caller_request = request(owner_user_id="untrusted-owner", data_classification="synthetic", processing_approved=True)
    with pytest.raises(AllCandidatesFailed):
        if service_kind == "stream":
            async for _event in service.stream(caller_request):
                pytest.fail("Unapproved processing must not yield answer text")
        else:
            await service.complete(caller_request)
    assert adapter.calls == []
    assert records[0].owner_user_id is None
    assert records[0].data_classification == "unknown"
    assert any("processing" in step for step in records[0].routing_path)


@pytest.mark.parametrize("streaming", [False, True])
async def test_trusted_request_ownership_and_effective_policy_survive_complete_and_stream(streaming: bool) -> None:
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    adapter = remote_adapter()
    records = []
    policy = RemoteProcessingPolicy(policy_id="reviewed-private-v1", private_providers=frozenset({"freellmpool"}))
    service = PoolRouter(
        {"freellmpool": adapter, "openrouter": FakeAdapter([])}, on_provenance=records.append,
        processing_policy=policy,
    )
    context = LLMRequestContext(owner_user_id="owner-a", study_id="study-a", data_classification="private")
    with llm_request_context(context):
        if streaming:
            events = [event async for event in service.stream(request())]
            result = events[-1]
        else:
            result = await service.complete(request())

    assert result.text == "Complete answer"
    assert records[0].owner_user_id == "owner-a"
    assert records[0].study_id == "study-a"
    assert records[0].task == TaskType.PERSONA_RESPONSE.value
    assert records[0].data_classification == "private"
    assert records[0].processing_policy_id == "reviewed-private-v1"
    assert records[0].processing_provider_allowlist == ("freellmpool",)
    with pytest.raises(ValueError, match="frozen"):
        records[0].owner_user_id = "another-owner"
    with pytest.raises(AllCandidatesFailed):
        await service.complete(request())


async def test_service_policy_denies_private_data_even_when_caller_marks_it_synthetic() -> None:
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    adapter = remote_adapter()
    records = []
    service = SingleAdapterLLMService(
        adapter, on_provenance=records.append,
        processing_policy=RemoteProcessingPolicy(policy_id="synthetic-only", synthetic_providers=frozenset({"freellmpool"})),
    )
    with llm_request_context(LLMRequestContext(owner_user_id="owner-a", data_classification="private")):
        with pytest.raises(AllCandidatesFailed):
            await service.complete(request(data_classification="synthetic", processing_approved=True))
    assert adapter.calls == []
    assert records[0].owner_user_id == "owner-a"
    assert records[0].data_classification == "private"
    assert records[0].processing_provider_allowlist == ()


async def test_conflicting_request_ownership_is_denied_and_cannot_relabel_provenance() -> None:
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    adapter = remote_adapter()
    records = []
    service = SingleAdapterLLMService(
        adapter, on_provenance=records.append,
        processing_policy=RemoteProcessingPolicy(policy_id="private-approved", private_providers=frozenset({"freellmpool"})),
    )
    with llm_request_context(LLMRequestContext(owner_user_id="authenticated-owner", data_classification="private")):
        with pytest.raises(AllCandidatesFailed):
            await service.complete(request(owner_user_id="claimed-other-owner"))
    assert adapter.calls == []
    assert records[0].owner_user_id == "authenticated-owner"


async def test_concurrent_server_contexts_never_mix_tenant_ownership() -> None:
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    service = SingleAdapterLLMService(
        remote_adapter(),
        processing_policy=RemoteProcessingPolicy(policy_id="private-approved", private_providers=frozenset({"freellmpool"})),
    )

    async def owned_request(owner: str):
        with llm_request_context(LLMRequestContext(owner_user_id=owner, study_id=f"study-{owner}", data_classification="private")):
            await asyncio.sleep(0)
            return await service.complete(request())

    first, second = await asyncio.gather(owned_request("first"), owned_request("second"))
    assert (first.provenance.owner_user_id, first.provenance.study_id) == ("first", "study-first")
    assert (second.provenance.owner_user_id, second.provenance.study_id) == ("second", "study-second")


def test_private_server_context_requires_immutable_ownership() -> None:
    from bebshax.llm.governance import LLMRequestContext

    with pytest.raises(ValueError, match="owner"):
        LLMRequestContext(data_classification="private")


def test_production_adapters_declare_remote_processing() -> None:
    from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter

    assert FreellmpoolAdapter.remote_processing is True
    assert OpenRouterAdapter.remote_processing is True


def test_new_provider_adapters_are_remote_by_default_and_only_the_fake_opts_out() -> None:
    from bebshax.llm.adapters.base import ProviderAdapter

    assert ProviderAdapter.remote_processing is True
    assert FakeAdapter.remote_processing is False


@pytest.mark.parametrize("approved_inner", [False, True])
async def test_primary_inner_destinations_are_limited_by_effective_server_policy(tmp_path, approved_inner: bool) -> None:
    from freellmpool.client import HTTPResult
    from freellmpool.models import Model, Provider
    from freellmpool.quota import QuotaStore

    from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    calls = []

    async def post(url, headers, body, timeout):
        calls.append(url)
        return HTTPResult(200, {"model": "verified-model", "choices": [
            {"message": {"content": "Complete answer"}, "finish_reason": "stop"},
        ]}, "")

    providers = [
        Provider(
            id=name, label=name, adapter="openai", base_url=f"https://{name}.example.com/v1", auth="none",
            models=(Model(name="verified-model", context=131072),),
        )
        for name in ["unapproved-inner", "approved-inner"]
    ]
    adapter = FreellmpoolAdapter(providers=providers, env={}, apost=post, quota=QuotaStore(path=tmp_path / "quota.json"))
    allowed = {"freellmpool", "approved-inner"} if approved_inner else {"freellmpool"}
    service = SingleAdapterLLMService(
        adapter, processing_policy=RemoteProcessingPolicy(policy_id="inner-approval", synthetic_providers=frozenset(allowed)),
    )
    try:
        with llm_request_context(LLMRequestContext(data_classification="synthetic")):
            if approved_inner:
                result = await service.complete(request())
                assert result.provider == "approved-inner"
                assert calls == ["https://approved-inner.example.com/v1/chat/completions"]
            else:
                with pytest.raises(AllCandidatesFailed):
                    await service.complete(request())
                assert calls == []
    finally:
        await adapter.aclose()


def openrouter_catalogue() -> list[dict]:
    return [{
        "id": "catalog/verified:free", "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["max_tokens", "temperature", "response_format"],
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
    }]


async def test_openrouter_tier_approval_without_upstream_approval_cannot_dispatch(monkeypatch) -> None:
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"model": "catalog/verified:free", "choices": [
            {"message": {"content": "Complete answer"}, "finish_reason": "stop"},
        ]})

    adapter = OpenRouterAdapter(
        api_key="synthetic-test-key", catalogue=openrouter_catalogue(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    service = SingleAdapterLLMService(
        adapter, processing_policy=RemoteProcessingPolicy(policy_id="tier-only", synthetic_providers=frozenset({"openrouter"})),
    )
    try:
        with llm_request_context(LLMRequestContext(data_classification="synthetic")):
            with pytest.raises(AllCandidatesFailed):
                await service.complete(request())
        assert calls == []
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("streaming", [False, True])
async def test_openrouter_dispatch_pins_approved_upstreams_free_price_and_processing_controls(monkeypatch, streaming: bool) -> None:
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
    from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    payloads = []

    def respond(http_request):
        payloads.append(json.loads(http_request.content))
        if streaming:
            events = [
                {"model": "catalog/verified:free", "choices": [{"delta": {"content": "Complete answer"}, "finish_reason": None}]},
                {"model": "catalog/verified:free", "choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
            return httpx.Response(200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n")
        return httpx.Response(200, json={"model": "catalog/verified:free", "choices": [
            {"message": {"content": "Complete answer"}, "finish_reason": "stop"},
        ]})

    adapter = OpenRouterAdapter(
        api_key="synthetic-test-key", catalogue=openrouter_catalogue(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    policy = RemoteProcessingPolicy(
        policy_id="reviewed-endpoint-policy", private_providers=frozenset({"openrouter"}),
        private_openrouter_upstreams=frozenset({"Reviewed Endpoint"}),
    )
    service = PoolRouter({"freellmpool": FakeAdapter([]), "openrouter": adapter}, processing_policy=policy)
    try:
        with llm_request_context(LLMRequestContext(owner_user_id="owner-a", data_classification="private")):
            if streaming:
                result = [event async for event in service.stream(request())][-1]
            else:
                result = await service.complete(request())
        assert result.text == "Complete answer"
        assert result.provenance.processing_openrouter_upstreams == ("Reviewed Endpoint",)
        assert payloads[0]["provider"] == {
            "only": ["Reviewed Endpoint"], "allow_fallbacks": False, "require_parameters": True,
            "data_collection": "deny", "max_price": {"prompt": 0, "completion": 0},
        }
    finally:
        await adapter.aclose()


async def test_owned_openrouter_client_cannot_use_environment_proxies_or_follow_redirects(monkeypatch) -> None:
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter

    original = httpx.AsyncClient
    configured = []

    def construct(**options):
        configured.append(options)
        return original(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})), **options)

    monkeypatch.setattr(httpx, "AsyncClient", construct)
    adapter = OpenRouterAdapter(api_key="synthetic-test-key")
    try:
        client = await adapter._get_client()
        assert configured[0]["trust_env"] is False
        assert configured[0]["follow_redirects"] is False
    finally:
        await adapter.aclose()
    assert client.is_closed