"""Quota-aware ranker: bucketed demotion, not continuous sorting.

Regression for the inversion bug: ONE recorded request on a capped provider
(49/50 remaining = 0.98 < 1.0) used to demote it below every uncapped route
for the rest of the day — the opposite of "use the free capacity we have".
"""

import uuid

from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.llm.quota import (
    PROVIDER_QUOTAS,
    QUOTA_DEMOTE_THRESHOLD,
    QuotaLedger,
    quota_aware_ranker,
)
from bebshax.llm.types import TaskType


def _prov(provider: str) -> ProvenanceRecord:
    return ProvenanceRecord(
        request_id=uuid.uuid4().hex,
        task=TaskType.PERSONA_GENERATION,
        served_by_provider=provider,
        input_tokens=5,
        output_tokens=5,
        success=True,
    )


def _entries(*providers: str):
    return [(None, RouteCandidate(provider=p, model=f"{p}-m")) for p in providers]


def _providers(ranked) -> list[str]:
    return [c.provider for _, c in ranked]


def _consume(ledger: QuotaLedger, provider: str, n: int) -> None:
    for _ in range(n):
        ledger.record(_prov(provider))


def test_one_success_on_a_capped_provider_leaves_order_unchanged() -> None:
    ledger = QuotaLedger()
    rank = quota_aware_ranker(ledger)
    entries = _entries("openrouter", "freellmpool", "ollama")
    _consume(ledger, "openrouter", 1)
    assert 0 < ledger.remaining_fraction("openrouter") < 1.0  # the old sort key moved
    assert _providers(rank(entries)) == ["openrouter", "freellmpool", "ollama"]


def test_ninety_percent_consumed_demotes_behind_healthy_remote_routes() -> None:
    ledger = QuotaLedger()
    rank = quota_aware_ranker(ledger)
    entries = _entries("openrouter", "freellmpool", "ollama")
    cap = PROVIDER_QUOTAS["openrouter"].rpd
    _consume(ledger, "openrouter", int(cap * 0.9))
    assert ledger.remaining_fraction("openrouter") < QUOTA_DEMOTE_THRESHOLD
    assert _providers(rank(entries)) == ["freellmpool", "ollama", "openrouter"]


def test_exhausted_provider_is_excluded() -> None:
    ledger = QuotaLedger()
    rank = quota_aware_ranker(ledger)
    entries = _entries("openrouter", "freellmpool", "ollama")
    _consume(ledger, "openrouter", PROVIDER_QUOTAS["openrouter"].rpd)
    assert ledger.remaining_fraction("openrouter") == 0.0
    assert _providers(rank(entries)) == ["freellmpool", "ollama"]


def test_historical_fake_names_have_no_special_ranking_tier() -> None:
    ledger = QuotaLedger()
    rank = quota_aware_ranker(ledger)
    _consume(ledger, "openrouter", PROVIDER_QUOTAS["openrouter"].rpd)  # exhausted

    assert _providers(rank(_entries("openrouter", "freellmpool", "ollama"))) == [
        "freellmpool",
        "ollama",
    ]
    assert _providers(rank(_entries("ollama", "openrouter", "freellmpool"))) == [
        "ollama",
        "freellmpool",
    ]
    assert _providers(rank(_entries("openrouter", "ollama", "freellmpool"))) == [
        "ollama",
        "freellmpool",
    ]


def test_demoted_bucket_orders_most_remaining_first_and_is_stable_otherwise() -> None:
    ledger = QuotaLedger()
    rank = quota_aware_ranker(ledger)
    entries = _entries("openrouter", "gemini", "freellmpool")
    _consume(ledger, "openrouter", PROVIDER_QUOTAS["openrouter"].rpd)  # 0.0 left
    _consume(ledger, "gemini", int(PROVIDER_QUOTAS["gemini"].rpd * 0.9))  # ~0.1 left
    assert _providers(rank(entries)) == ["freellmpool", "gemini"]
    # multiple models of one healthy provider keep their relative order
    many = _entries("freellmpool") + [
        (None, RouteCandidate(provider="openrouter", model="a")),
        (None, RouteCandidate(provider="openrouter", model="b")),
    ]
    healthy_rank = quota_aware_ranker(QuotaLedger())
    assert [c.model for _, c in healthy_rank(many)] == ["freellmpool-m", "a", "b"]
