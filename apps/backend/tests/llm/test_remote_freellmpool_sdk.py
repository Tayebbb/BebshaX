import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
from freellmpool.aio import AsyncPool
from freellmpool.client import HTTPResult
from freellmpool.models import Model, Provider
from freellmpool.quota import QuotaStore

from bebshax.llm import ChatMessage, LLMRequest, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context


@pytest.fixture
async def approved_primary_policy() -> AsyncIterator[RemoteProcessingPolicy]:
    with llm_request_context(LLMRequestContext(data_classification="synthetic")):
        yield RemoteProcessingPolicy(
            policy_id="synthetic-sdk-fixture",
            synthetic_providers=frozenset({"freellmpool", "catalog-primary"}),
        )


def provider(name="catalog-primary", *, model="chat", context=131072, rpd=0):
    return Provider(
        id=name, label=name, adapter="openai", base_url=f"https://{name}.example.com/v1",
        auth="none", models=(Model(name=model, context=context, rpd=rpd),),
    )


def request(**changes):
    return LLMRequest(
        task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="complete synthetic context")],
        **changes,
    )


def ok(text='{"ok": true}', *, finish="stop", tokens=32):
    return HTTPResult(200, {
        "model": "actual-reported-model",
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 8, "completion_tokens": tokens},
    }, "")


def make_adapter(tmp_path, apost, *, providers=None, **changes):
    configured = providers if providers is not None else [provider()]
    changes.setdefault("json_models", frozenset((entry.id, model.name) for entry in configured for model in entry.models))
    return FreellmpoolAdapter(
        providers=configured,
        env={}, quota=QuotaStore(path=tmp_path / "quota.json"), apost=apost, **changes,
    )


async def test_real_sdk_gets_full_context_json_and_exact_thinking_model_limit(tmp_path):
    calls = []

    async def post(url, headers, body, timeout):
        calls.append(body)
        return ok()

    adapter = make_adapter(tmp_path, post, providers=[provider(model="deepseek-r1")])
    try:
        [candidate] = await adapter.candidates()
        result = await adapter.complete(candidate, request(json_mode=True, max_output_tokens=32, temperature=0.3))
        assert isinstance(await adapter._get_pool(), AsyncPool)
        assert calls[0]["response_format"] == {"type": "json_object"}
        assert calls[0]["max_tokens"] == 32
        assert calls[0]["temperature"] == 0.3
        assert calls[0]["messages"][0]["content"] == "complete synthetic context"
        assert result.model == "actual-reported-model"
        assert result.finish_reason == "stop"
        assert result.observations[0].requested_model == "deepseek-r1"
        assert result.observations[0].reported_model == "actual-reported-model"
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("status, kind", [(429, FailureKind.RATE_LIMITED), (401, FailureKind.AUTH_INVALID), (503, FailureKind.SERVER_ERROR)])
async def test_actual_asyncpool_aggregated_failures_keep_structured_status_and_hints(tmp_path, status, kind):
    calls = []

    async def post(url, headers, body, timeout):
        calls.append(url)
        return HTTPResult(status, {"error": {"message": "synthetic failure"}}, "", {"Retry-After": "3600"})

    adapter = make_adapter(tmp_path, post, providers=[provider("first"), provider("second")])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request())
        assert len(calls) == 2
        assert error.value.kind == kind
        assert error.value.retry_after_s == 3600
        assert [observation.status_code for observation in error.value.observations] == [status, status]
        assert all(observation.consumption == "unknown" for observation in error.value.observations)
    finally:
        await adapter.aclose()


async def test_actual_sdk_cooling_targets_are_excluded_not_merely_demoted(tmp_path):
    calls = []

    async def post(url, headers, body, timeout):
        calls.append(url)
        return HTTPResult(429, {"error": {"message": "rate limit"}}, "", {"Retry-After": "3600"})

    adapter = make_adapter(tmp_path, post)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, request())
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, request())
        assert len(calls) == 1
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("text, finish", [("prose", "stop"), ("[]", "stop"), ('{"partial":', "length")])
async def test_real_sdk_cannot_accept_malformed_or_truncated_structured_output(tmp_path, text, finish):
    async def post(*args):
        return ok(text, finish=finish)

    adapter = make_adapter(tmp_path, post)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request(json_mode=True, max_output_tokens=32))
        assert error.value.kind == FailureKind.MALFORMED_RESPONSE
        assert error.value.observations[0].consumption == "known"
    finally:
        await adapter.aclose()


async def test_unknown_context_never_authorizes_a_virtual_million_token_route(tmp_path):
    calls = []

    async def post(*args):
        calls.append(True)
        return ok()

    adapter = make_adapter(tmp_path, post, providers=[provider(context=None)])
    try:
        assert await adapter.candidates() == []
        with pytest.raises(AttemptFailed):
            await adapter.complete(RouteCandidate(provider="freellmpool", model="auto"), request())
        assert not calls
    finally:
        await adapter.aclose()


async def test_app_catalog_exposes_a_context_verified_keyless_primary_candidate(tmp_path):
    async def post(*args):
        pytest.fail("Catalog inspection must not issue an inference request")

    adapter = FreellmpoolAdapter(
        env={}, quota=QuotaStore(path=tmp_path / "quota.json"), apost=post,
    )
    try:
        candidates = await adapter.candidates_for(request())
        assert candidates, "The reviewed application catalog must retain a usable primary route"
        assert all(candidate.context_window > 0 for candidate in candidates)
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("classification", ["synthetic", "private"])
async def test_verified_app_catalog_dispatch_preserves_context_and_never_infers_private_consent(tmp_path, classification):
    from bebshax.llm import AllCandidatesFailed

    calls = []
    records = []

    async def post(url, headers, body, timeout):
        calls.append((url, body))
        return ok("Complete synthetic answer")

    adapter = FreellmpoolAdapter(
        env={}, quota=QuotaStore(path=tmp_path / "quota.json"), apost=post,
    )
    service = SingleAdapterLLMService(
        adapter, on_provenance=records.append,
        processing_policy=RemoteProcessingPolicy(
            policy_id="verified-catalog-synthetic-fixture",
            synthetic_providers=frozenset({"freellmpool", "kilo"}),
        ),
    )
    original = request(max_output_tokens=64)
    context = LLMRequestContext(owner_user_id="usr_catalog_fixture", data_classification=classification)
    try:
        with llm_request_context(context):
            if classification == "private":
                with pytest.raises(AllCandidatesFailed):
                    await service.complete(original)
                assert calls == []
            else:
                result = await service.complete(original)
                assert result.provider == "kilo"
                assert len(calls) == 1
                assert calls[0][1]["model"] == "stepfun/step-3.7-flash:free"
                assert calls[0][1]["messages"] == [message.model_dump() for message in original.messages]
                assert calls[0][1]["max_tokens"] == 64
        assert records[0].owner_user_id == "usr_catalog_fixture"
        assert records[0].data_classification == classification
    finally:
        await service.aclose()
        await adapter.aclose()


@pytest.mark.parametrize("json_mode", [False, True])
async def test_checked_in_catalog_routes_approved_synthetic_stream_with_full_context(tmp_path, monkeypatch, json_mode: bool) -> None:
    from bebshax.llm import LLMResult, PoolRouter
    from bebshax.llm.adapters.base import StreamDelta
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter

    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    primary_payloads = []
    secondary_payloads = []
    answer = '{"answer":"Complete synthetic answer"}' if json_mode else "Complete synthetic answer"

    async def primary_post(url, headers, body, timeout):
        primary_payloads.append(body)
        return ok(answer)

    def secondary_post(incoming: httpx.Request) -> httpx.Response:
        assert incoming.method == "POST"
        secondary_payloads.append(json.loads(incoming.content))
        payload = {
            "model": "fixture/reported-structured:free",
            "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 32},
        }
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"},
            content="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n",
        )

    primary = FreellmpoolAdapter(
        env={}, quota=QuotaStore(path=tmp_path / "quota.json"), apost=primary_post,
    )
    secondary = OpenRouterAdapter(
        api_key="synthetic-fixture-key",
        catalogue=[{
            "id": "fixture/structured:free", "context_length": 65536,
            "pricing": {"prompt": "0", "completion": "0"},
            "supported_parameters": ["max_tokens", "response_format"],
        }],
        client=httpx.AsyncClient(transport=httpx.MockTransport(secondary_post)),
    )
    records = []
    service = PoolRouter(
        {"freellmpool": primary, "openrouter": secondary}, on_provenance=records.append,
        processing_policy=RemoteProcessingPolicy(
            policy_id="checked-in-catalog-stream-fixture",
            synthetic_providers=frozenset({"freellmpool", "kilo", "openrouter"}),
            synthetic_openrouter_upstreams=frozenset({"Fixture Endpoint"}),
        ),
    )
    original = LLMRequest(
        task=TaskType.PERSONA_RESPONSE,
        messages=[
            ChatMessage(role="system", content="Complete synthetic identity, memory and evidence. " * 200),
            ChatMessage(role="user", content="A synthetic research question."),
        ],
        json_mode=json_mode, max_output_tokens=64,
    )
    try:
        with llm_request_context(LLMRequestContext(owner_user_id="usr_stream_fixture", data_classification="synthetic")):
            events = [event async for event in service.stream(original)]
        result = events[-1]
        assert isinstance(result, LLMResult)
        assert result.provider == ("openrouter" if json_mode else "kilo")
        assert result.text == answer
        assert "".join(event.text for event in events if isinstance(event, StreamDelta)) == answer
        assert len(secondary_payloads) == int(json_mode)
        assert len(primary_payloads) == int(not json_mode)
        [sent] = secondary_payloads if json_mode else primary_payloads
        assert sent["messages"] == [message.model_dump() for message in original.messages]
        assert sent["max_tokens"] == original.max_output_tokens
        if json_mode:
            assert sent["stream"] is True
            assert sent["response_format"] == {"type": "json_object"}
            assert sent["provider"]["only"] == ["Fixture Endpoint"]
            assert sent["provider"]["allow_fallbacks"] is False
        assert records == [result.provenance]
        assert records[0].owner_user_id == "usr_stream_fixture"
        assert records[0].processing_policy_id == "checked-in-catalog-stream-fixture"
        assert records[0].attempts[-1].observations[-1].finish_reason == "stop"
    finally:
        await service.aclose()
        await primary.aclose()
        await secondary.aclose()


async def test_hidden_answer_cache_cannot_be_enabled_by_legacy_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FREELLMPOOL_CACHE_TTL", "3600")
    calls = []

    async def post(*args):
        calls.append(True)
        return ok()

    adapter = make_adapter(tmp_path, post)
    try:
        [candidate] = await adapter.candidates()
        await adapter.complete(candidate, request())
        await adapter.complete(candidate, request())
        assert len(calls) == 2
        assert (await adapter._get_pool()).stats["cache_hits"] == 0
    finally:
        await adapter.aclose()


async def test_cancellation_in_actual_apost_keeps_active_target_and_unknown_consumption(tmp_path, approved_primary_policy):
    entered = asyncio.Event()

    async def post(*args):
        entered.set()
        await asyncio.Event().wait()

    adapter = make_adapter(tmp_path, post)
    records = []
    service = SingleAdapterLLMService(adapter, on_provenance=records.append, processing_policy=approved_primary_policy)
    running = asyncio.create_task(service.complete(request()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        [attempt] = records[0].attempts
        assert attempt.failure_kind is None
        assert attempt.observations[0].provider == "catalog-primary"
        assert attempt.observations[0].outcome == "aborted"
        assert attempt.observations[0].consumption == "unknown"
        assert (await adapter._get_pool()).stats["requests"] == 0
    finally:
        if not running.done():
            running.cancel()
        await adapter.aclose()


async def test_transport_programming_error_is_not_aggregated_as_provider_outage(tmp_path):
    calls = []

    async def post(*args):
        calls.append(True)
        raise RuntimeError("synthetic adapter bug")

    adapter = make_adapter(tmp_path, post, providers=[provider("first"), provider("second")])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request())
        assert error.value.kind == FailureKind.INTERNAL_ERROR
        assert len(calls) == 1
    finally:
        await adapter.aclose()


async def test_rejected_generated_answer_still_uses_the_published_daily_allowance(tmp_path):
    calls = []

    async def post(*args):
        calls.append(True)
        return ok("prose instead of requested JSON")

    adapter = make_adapter(tmp_path, post, providers=[provider(rpd=1)])
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, request(json_mode=True))
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, request(json_mode=True))
        assert len(calls) == 1
    finally:
        await adapter.aclose()


async def test_app_owned_catalog_ignores_legacy_configuration_and_cache_controls(tmp_path, monkeypatch):
    config = tmp_path / "providers.toml"
    config.write_text('[[provider]]\nid="verified-new"\nbase_url="https://new.example.com/v1"\nauth="none"\n[[provider.models]]\nname="approved-model"\ncontext=131072\n', encoding="utf-8")
    monkeypatch.setenv("FREELLMPOOL_CONFIG", str(tmp_path / "must-not-be-read.toml"))
    monkeypatch.setenv("FREELLMPOOL_ALLOW_LOCAL_PROVIDERS", "true")
    calls = []

    async def post(url, *args):
        calls.append(url)
        return ok()

    adapter = FreellmpoolAdapter(env={}, provider_config=config, apost=post, quota=QuotaStore(path=tmp_path / "quota.json"))
    try:
        [candidate] = await adapter.candidates()
        await adapter.complete(candidate, request())
        assert calls == ["https://new.example.com/v1/chat/completions"]
        assert not {"ollama", "openrouter"}.intersection(provider.id for provider in (await adapter._get_pool()).providers)
    finally:
        await adapter.aclose()


async def test_missing_primary_configuration_fails_closed_and_allows_independent_secondary(tmp_path):
    from bebshax.llm import PoolRouter
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute

    primary = FreellmpoolAdapter(env={}, provider_config=tmp_path / "missing.toml")
    secondary = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="openrouter", model="remote"), reply="secondary answer")])
    service = PoolRouter({"freellmpool": primary, "openrouter": secondary})
    try:
        result = await service.complete(request())
        assert result.text == "secondary answer"
        assert any("discovery" in step and "freellmpool" in step for step in result.provenance.routing_path)
    finally:
        await primary.aclose()


async def test_cancelled_upstream_does_not_receive_a_synthetic_latency_sample(tmp_path, approved_primary_policy):
    entered = asyncio.Event()

    async def post(*args):
        entered.set()
        await asyncio.Event().wait()

    adapter = make_adapter(tmp_path, post)
    records = []
    running = asyncio.create_task(SingleAdapterLLMService(adapter, on_provenance=records.append, processing_policy=approved_primary_policy).complete(request()))
    try:
        await entered.wait()
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        [attempt] = records[0].attempts
        assert attempt.latency_ms is None
        assert attempt.elapsed_ms is not None
        assert attempt.observations[0].latency_ms is None
    finally:
        if not running.done():
            running.cancel()
        await adapter.aclose()


async def test_total_deadline_keeps_active_inner_observation_without_latency(tmp_path, approved_primary_policy):
    from bebshax.llm import AllCandidatesFailed

    async def post(*args):
        await asyncio.Event().wait()

    adapter = make_adapter(tmp_path, post)
    records = []
    try:
        # Generous enough for a loaded CI runner to start the attempt before it expires.
        deadline = asyncio.get_running_loop().time() + 0.5
        with pytest.raises(AllCandidatesFailed):
            await SingleAdapterLLMService(adapter, on_provenance=records.append, processing_policy=approved_primary_policy).complete(request(), deadline_at=deadline)
        [attempt] = records[0].attempts
        assert attempt.observations[0].provider == "catalog-primary"
        # The deadline cancels the in-flight attempt; a task that outlives the
        # 20 ms cancel grace is retained and records its outcome as soon as the
        # loop runs it again, so settle before asserting (bounded, no fixed sleep).
        for _ in range(200):
            if attempt.observations[0].outcome != "unknown":
                break
            await asyncio.sleep(0.005)
        assert attempt.observations[0].outcome == "aborted", attempt.model_dump(mode="json")
        assert attempt.latency_ms is None
        assert attempt.elapsed_ms is not None
    finally:
        await adapter.aclose()


async def test_metric_replay_accepts_only_verified_primary_requested_targets(tmp_path):
    async def post(*args):
        return ok()

    adapter = make_adapter(tmp_path, post)
    try:
        count = await adapter.seed_metrics([
            ("openrouter", "catalog/chat:free", 20.0),
            ("catalog-primary", "chat", 10.0),
            ("catalog-primary", "unknown-reported-alias", 30.0),
        ])
        assert count == 1
    finally:
        await adapter.aclose()


async def test_primary_cooldown_callback_and_restore_use_concrete_account_keys(tmp_path, monkeypatch):
    changes = []
    calls = []

    async def post(url, *args):
        calls.append(url)
        return HTTPResult(429, {"error": {"message": "limit"}}, "", {"Retry-After": "3600"})

    adapter = make_adapter(tmp_path, post, on_cooldown_change=lambda *args: changes.append(args))
    try:
        [candidate] = await adapter.candidates()
        assert adapter._transport is not None
        monkeypatch.setattr(adapter._transport, "_clock", lambda: 0.0)
        with pytest.raises(AttemptFailed):
            await adapter.complete(candidate, request())
        assert changes == [("catalog-primary", "*", 3600.0)]
    finally:
        await adapter.aclose()
    restored = make_adapter(tmp_path, post, initial_cooldowns={("catalog-primary", "*"): time.monotonic() + 3600})
    try:
        with pytest.raises(AttemptFailed):
            await restored.complete(RouteCandidate(provider="freellmpool", model="auto"), request())
        assert len(calls) == 1
    finally:
        await restored.aclose()


async def test_managed_primary_failures_do_not_cool_the_entire_virtual_tier(tmp_path, monkeypatch, approved_primary_policy):
    from bebshax.llm import PoolRouter
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute

    changes = []

    async def post(*args):
        return HTTPResult(429, {"error": {"message": "limit"}}, "", {"Retry-After": "3600"})

    adapter = make_adapter(tmp_path, post, on_cooldown_change=lambda *args: changes.append(args))
    secondary = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="openrouter", model="remote"))])
    service = PoolRouter({"freellmpool": adapter, "openrouter": secondary}, on_cooldown_change=lambda *args: changes.append(args), processing_policy=approved_primary_policy)
    try:
        await adapter.candidates()
        assert adapter._transport is not None
        monkeypatch.setattr(adapter._transport, "_clock", lambda: 0.0)
        result = await service.complete(request())
        assert result.provider == "openrouter"
        assert changes == [("catalog-primary", "*", 3600.0)]
    finally:
        await adapter.aclose()


async def test_unknown_json_capability_does_not_remove_verified_plain_chat(tmp_path) -> None:
    async def post(*args):
        return ok("Complete plain answer")

    adapter = FreellmpoolAdapter(providers=[provider()], env={}, apost=post, quota=QuotaStore(path=tmp_path / "quota.json"))
    try:
        [candidate] = await adapter.candidates_for(request())
        assert candidate.context_window == 131072
        assert candidate.supports_json is False
        assert (await adapter.complete(candidate, request())).text == "Complete plain answer"
    finally:
        await adapter.aclose()


async def test_unknown_json_capability_never_authorizes_structured_dispatch(tmp_path) -> None:
    calls = []

    async def post(*args):
        calls.append(True)
        return ok()

    adapter = FreellmpoolAdapter(providers=[provider()], env={}, apost=post, quota=QuotaStore(path=tmp_path / "quota.json"))
    try:
        assert await adapter.candidates_for(request(json_mode=True)) == []
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(RouteCandidate(provider="freellmpool", model="auto"), request(json_mode=True))
        assert error.value.kind == FailureKind.CAPABILITY_UNSUPPORTED
        assert calls == []
    finally:
        await adapter.aclose()


async def test_application_catalog_explicitly_enables_verified_json_capability(tmp_path) -> None:
    config = tmp_path / "providers.toml"
    config.write_text(
        '[[provider]]\nid="json-approved"\nbase_url="https://json.example.com/v1"\nauth="none"\n'
        '[[provider.models]]\nname="json-model"\ncontext=16384\nsupports_json=true\n', encoding="utf-8",
    )
    calls = []

    async def post(url, headers, body, timeout):
        calls.append((url, body))
        return ok()

    adapter = FreellmpoolAdapter(env={}, provider_config=config, apost=post, quota=QuotaStore(path=tmp_path / "quota.json"))
    try:
        [candidate] = await adapter.candidates_for(request(json_mode=True))
        assert candidate.supports_json is True
        assert candidate.context_window == 16384
        await adapter.complete(candidate, request(json_mode=True))
        assert calls[0][0] == "https://json.example.com/v1/chat/completions"
        assert calls[0][1]["response_format"] == {"type": "json_object"}
    finally:
        await adapter.aclose()


async def test_json_virtual_context_excludes_larger_plain_only_models(tmp_path) -> None:
    adapter = FreellmpoolAdapter(
        providers=[provider("small-json", context=8192), provider("large-plain", context=200000)],
        env={}, quota=QuotaStore(path=tmp_path / "quota.json"), json_models=frozenset({("small-json", "chat")}),
    )
    try:
        [structured] = await adapter.candidates_for(request(json_mode=True))
        [plain] = await adapter.candidates_for(request())
        assert structured.context_window == 8192
        assert plain.context_window == 200000
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("blocked_by", ["cooldown", "quota", "model_quota"])
async def test_request_context_metadata_excludes_unavailable_larger_primary(tmp_path, blocked_by: str) -> None:
    async def post(*args):
        pytest.fail("Request-aware discovery must not make an inference call")

    quota = QuotaStore(path=tmp_path / "quota.json")
    if blocked_by == "model_quota":
        quota.record("large-primary", "chat")
    options = {
        "cooldown": {"initial_cooldowns": {("large-primary", "*"): time.monotonic() + 3600}},
        "quota": {"quota_remaining": lambda provider_id: 0 if provider_id == "large-primary" else 1},
        "model_quota": {},
    }[blocked_by]
    adapter = FreellmpoolAdapter(
        env={}, apost=post, quota=quota,
        providers=[provider("small-primary", context=8192), provider("large-primary", context=200000, rpd=1)],
        **options,
    )
    try:
        [candidate] = await adapter.candidates_for(request())
        assert candidate.context_window == 8192
    finally:
        await adapter.aclose()


async def test_real_sdk_gemini_preserves_json_contract_and_exact_output_budget(tmp_path) -> None:
    calls = []

    async def post(url, headers, body, timeout):
        calls.append(body)
        return HTTPResult(200, {
            "modelVersion": "verified-gemini-model",
            "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 32},
        }, "")

    target = replace(provider(), adapter="gemini")
    adapter = make_adapter(tmp_path, post, providers=[target])
    try:
        [candidate] = await adapter.candidates_for(request(json_mode=True))
        result = await adapter.complete(candidate, request(json_mode=True, max_output_tokens=32))
        assert calls[0]["generationConfig"]["responseMimeType"] == "application/json"
        assert calls[0]["generationConfig"]["maxOutputTokens"] == 32
        assert result.model == "verified-gemini-model"
        assert result.observations[0].finish_reason == "STOP"
        assert result.usage.output_tokens == 32
    finally:
        await adapter.aclose()


async def test_actual_sdk_skips_plain_only_and_small_context_inner_models_before_http(tmp_path) -> None:
    calls = []

    async def post(url, headers, body, timeout):
        calls.append(body["model"])
        return ok()

    mixed = replace(provider(), models=(
        Model(name="plain-only", context=131072),
        Model(name="json-too-small", context=8),
        Model(name="json-fitting", context=131072),
    ))
    adapter = make_adapter(tmp_path, post, providers=[mixed], json_models=frozenset({
        (mixed.id, "json-too-small"), (mixed.id, "json-fitting"),
    }))
    try:
        [candidate] = await adapter.candidates_for(request(json_mode=True))
        result = await adapter.complete(candidate, request(json_mode=True))
        assert calls == ["json-fitting"]
        assert all(observation.consumption == "none" for observation in result.observations if observation.outcome == "skipped")
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("transport_error, kind", [(httpx.ReadTimeout("synthetic timeout"), FailureKind.TIMEOUT), (httpx.ConnectError("synthetic refusal"), FailureKind.CONNECTION)])
async def test_actual_sdk_transport_failures_keep_the_original_failure_class(tmp_path, transport_error, kind) -> None:
    async def post(*args):
        raise transport_error

    adapter = make_adapter(tmp_path, post)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request())
        assert error.value.kind == kind
        assert error.value.observations[0].failure_kind == kind
        assert error.value.observations[0].consumption == "unknown"
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("admission", ["remaining", "reservation"])
async def test_actual_sdk_account_admission_denial_never_posts(tmp_path, admission: str) -> None:
    calls = []

    async def post(*args):
        calls.append(True)
        return ok()

    options = {"quota_remaining": lambda provider_id: 0} if admission == "remaining" else {"reserve_attempt": lambda provider_id: None}
    adapter = make_adapter(tmp_path, post, **options)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request())
        assert error.value.kind == FailureKind.QUOTA_EXHAUSTED
        assert error.value.observations[0].outcome == "skipped"
        assert error.value.observations[0].consumption == "none"
        assert calls == []
    finally:
        await adapter.aclose()


async def test_primary_observation_retains_the_account_reservation_id(tmp_path) -> None:
    async def post(*args):
        return ok()

    adapter = make_adapter(tmp_path, post, reserve_attempt=lambda provider_id: "test-reservation")
    try:
        [candidate] = await adapter.candidates()
        result = await adapter.complete(candidate, request())
        assert result.observations[0].account_reservation_id == "test-reservation"
    finally:
        await adapter.aclose()


async def test_cooldown_persistence_programming_error_stops_sdk_fallback(tmp_path) -> None:
    calls = []

    async def post(*args):
        calls.append(True)
        return HTTPResult(429, {}, "", {"Retry-After": "3600"})

    def broken_persistence(*args):
        raise RuntimeError("synthetic callback bug")

    adapter = make_adapter(tmp_path, post, providers=[provider("first"), provider("second")], on_cooldown_change=broken_persistence)
    try:
        [candidate] = await adapter.candidates()
        with pytest.raises(AttemptFailed) as error:
            await adapter.complete(candidate, request())
        assert error.value.kind == FailureKind.INTERNAL_ERROR
        assert len(calls) == 1
    finally:
        await adapter.aclose()


@pytest.mark.parametrize("valid_body", [False, True])
async def test_primary_owned_http_client_disables_environment_proxies_and_closes(tmp_path, monkeypatch, valid_body: bool) -> None:
    original_client = httpx.AsyncClient
    clients = []
    options_seen = []

    def respond(http_request):
        assert str(http_request.url) == "https://catalog-primary.example.com/v1/chat/completions"
        if not valid_body:
            return httpx.Response(200, text="not a completion envelope")
        return httpx.Response(200, json=ok().body)

    def construct(**options):
        options_seen.append(options)
        client = original_client(transport=httpx.MockTransport(respond), **options)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", construct)
    adapter = make_adapter(tmp_path, None)
    try:
        [candidate] = await adapter.candidates()
        if valid_body:
            assert (await adapter.complete(candidate, request())).text == '{"ok": true}'
        else:
            with pytest.raises(AttemptFailed) as error:
                await adapter.complete(candidate, request())
            assert error.value.kind == FailureKind.MALFORMED_RESPONSE
        assert options_seen == [{"follow_redirects": False, "trust_env": False}]
    finally:
        await adapter.aclose()
    assert clients[0].is_closed