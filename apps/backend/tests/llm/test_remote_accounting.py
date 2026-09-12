import asyncio
import json

import httpx
import pytest

from bebshax.llm import ChatMessage, LLMRequest, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord, ProviderObservation
from bebshax.llm.quota import PROVIDER_QUOTAS, QuotaLedger, quota_aware_ranker


def provenance(*observations, cached=False):
    return ProvenanceRecord(
        request_id="synthetic-request", task="PERSONA_RESPONSE", success=True,
        served_by_provider="openrouter", served_by_model="reported", input_tokens=10, output_tokens=5,
        attempts=[AttemptRecord(attempt_number=1, provider="openrouter", model="requested:free", success=True, cached=cached, observations=list(observations))],
    )


def test_cached_success_does_not_consume_another_upstream_request():
    ledger = QuotaLedger()
    ledger.record(provenance(cached=True))
    assert ledger.used_today("openrouter") == (0, 0)
    row = next(row for row in ledger.snapshot() if row["provider"] == "openrouter")
    assert row["cached_today"] == 1


def test_failed_rejected_and_cancelled_inner_attempts_retain_consumption():
    ledger = QuotaLedger()
    record = provenance(
        ProviderObservation(provider="primary", requested_model="first", outcome="failed", consumption="unknown", failure_kind=FailureKind.RATE_LIMITED),
        ProviderObservation(provider="primary", requested_model="second", outcome="failed", consumption="known", input_tokens=10, output_tokens=5, failure_kind=FailureKind.MALFORMED_RESPONSE),
        ProviderObservation(provider="openrouter", requested_model="third", outcome="aborted", consumption="unknown"),
    )
    record.success = False
    ledger.record(record)
    assert ledger.used_today("primary") == (2, 15)
    assert ledger.used_today("openrouter") == (1, 0)
    rows = {row["provider"]: row for row in ledger.snapshot()}
    assert rows["primary"]["unknown_consumption_today"] == 1
    assert rows["openrouter"]["aborted_today"] == 1


def test_skipped_routes_do_not_consume_quota():
    ledger = QuotaLedger()
    ledger.record(provenance(ProviderObservation(provider="openrouter", requested_model="blocked", outcome="skipped", consumption="none")))
    assert ledger.used_today("openrouter") == (0, 0)


def test_recording_and_replaying_the_same_provenance_is_idempotent():
    ledger = QuotaLedger()
    record = provenance(ProviderObservation(provider="openrouter", requested_model="free", outcome="succeeded", consumption="known", input_tokens=10, output_tokens=5))
    ledger.record(record)
    ledger.record(record)
    ledger.seed_provenance([record])
    assert ledger.used_today("openrouter") == (1, 15)


def test_exhausted_account_is_excluded_not_only_demoted():
    ledger = QuotaLedger()
    ledger.seed({"openrouter": 50}, {})
    adapter = FakeAdapter([])
    excluded = (adapter, RouteCandidate(provider="openrouter", model="free"))
    eligible = (adapter, RouteCandidate(provider="remote", model="free"))
    assert quota_aware_ranker(ledger)([excluded, eligible]) == [eligible]


def test_active_quota_table_has_no_local_inference_tier():
    assert "ollama" not in PROVIDER_QUOTAS


def test_attempt_reservation_is_atomic_and_provenance_does_not_double_charge() -> None:
    ledger = QuotaLedger()
    ledger.seed({"openrouter": 49}, {})
    reservation = ledger.reserve_attempt("openrouter")
    assert reservation is not None
    assert ledger.reserve_attempt("openrouter") is None
    assert ledger.used_today("openrouter") == (50, 0)
    ledger.record(provenance(ProviderObservation(
        provider="openrouter", requested_model="free", outcome="failed", consumption="known",
        input_tokens=10, output_tokens=5, account_reservation_id=reservation,
    )))
    assert ledger.used_today("openrouter") == (50, 15)
    row = next(row for row in ledger.snapshot() if row["provider"] == "openrouter")
    assert row["attempted_today"] == 1
    assert row["failed_today"] == 1


@pytest.mark.parametrize("streaming", [False, True])
async def test_concurrent_openrouter_requests_cannot_both_spend_the_last_account_slot(monkeypatch, streaming: bool) -> None:
    from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter

    monkeypatch.delenv("BEBSHAX_OPENROUTER_MODELS", raising=False)
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []
    ledger = QuotaLedger()
    ledger.seed({"openrouter": 49}, {})

    async def respond(request):
        calls.append(request)
        entered.set()
        await release.wait()
        if streaming:
            frame = {"model": "catalog/verified:free", "choices": [{"delta": {"content": "Complete answer"}, "finish_reason": "stop"}]}
            return httpx.Response(200, text=f"data: {json.dumps(frame)}\n\ndata: [DONE]\n\n")
        return httpx.Response(200, json={
            "model": "catalog/verified:free",
            "choices": [{"message": {"content": "Complete answer"}, "finish_reason": "stop"}],
        })

    adapter = OpenRouterAdapter(
        api_key="synthetic-test-key", reserve_attempt=ledger.reserve_attempt,
        catalogue=[{
            "id": "catalog/verified:free", "context_length": 131072,
            "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": ["max_tokens"],
        }], client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    [candidate] = await adapter.candidates()
    request = LLMRequest(task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="Complete context")])

    async def call(llm_request):
        if streaming:
            return [event async for event in adapter.stream(candidate, llm_request)][-1].completion
        return await adapter.complete(candidate, llm_request)

    first = asyncio.create_task(call(request))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        with pytest.raises(AttemptFailed) as error:
            await call(request.retry_copy())
        assert error.value.kind == FailureKind.QUOTA_EXHAUSTED
        assert len(calls) == 1
        release.set()
        result = await first
        assert result.observations[0].account_reservation_id is not None
        assert ledger.used_today("openrouter") == (50, 0)
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)
        await adapter.aclose()


async def test_factory_shares_attempt_reservations_across_primary_and_secondary(tmp_path, monkeypatch) -> None:
    from bebshax.llm.adapters.factory import build_default_adapters
    from bebshax.llm.quota import ProviderQuota

    ledger = QuotaLedger()
    monkeypatch.setitem(PROVIDER_QUOTAS, "catalog-primary", ProviderQuota(rpd=1))
    config = tmp_path / "providers.toml"
    config.write_text(
        '[[provider]]\nid="catalog-primary"\nbase_url="https://primary.example.com/v1"\nauth="none"\n'
        '[[provider.models]]\nname="chat"\ncontext=131072\n', encoding="utf-8",
    )
    adapters = build_default_adapters(quota_ledger=ledger, provider_config=config)
    try:
        await adapters["freellmpool"].candidates()
        assert adapters["freellmpool"]._transport._reserve_attempt("catalog-primary") is not None
        assert ledger.reserve_attempt("catalog-primary") is None
        assert adapters["openrouter"]._reserve_attempt("openrouter") is not None
        assert ledger.used_today("openrouter") == (1, 0)
    finally:
        for adapter in adapters.values():
            await adapter.aclose()