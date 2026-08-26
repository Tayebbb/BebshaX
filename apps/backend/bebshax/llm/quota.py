"""Free-tier capacity ledger (AI plan §10) — quotas as DATA, counting in memory.

PROVIDER_QUOTAS holds published per-provider daily/minute caps (verified where
possible; editable table, never code branches). QuotaLedger counts consumption
from ProvenanceRecords as they stream through `on_provenance` (seeded from the
llm_requests table at startup) and exposes `remaining_fraction(provider)` for
the quota-aware ranker and the capacity endpoint. Keys are the CONCRETE
serving-provider names recorded in provenance (never the virtual "auto").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bebshax.llm.provenance import ProvenanceRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderQuota:
    rpd: int | None = None  # requests/day; None = no published cap
    tpd: int | None = None  # tokens/day
    note: str = ""


# Verified 2026-08-25/26 where noted; conservative placeholders elsewhere —
# correct them at key-signup time (docs/AI_IMPLEMENTATION_PLAN.md §10).
PROVIDER_QUOTAS: dict[str, ProviderQuota] = {
    "openrouter": ProviderQuota(rpd=50, note="verified: free tier at $0, 20 rpm"),
    "ollama": ProviderQuota(note="local — unlimited"),
    "groq": ProviderQuota(rpd=14_400, tpd=500_000, note="verify at signup"),
    "gemini": ProviderQuota(rpd=250, note="verify at signup; resets midnight PT"),
    "mistral": ProviderQuota(tpd=33_000_000, note="≈1B/month experiment plan; verify"),
    "cerebras": ProviderQuota(tpd=1_000_000, note="verify at signup"),
}
# Keyless community providers reached via freellmpool (llm7, pollinations, …)
# publish no hard caps; treat as unlimited and let 429s/cooldowns govern.
DEFAULT_QUOTA = ProviderQuota()


@dataclass
class _DayCounter:
    day: str = ""
    requests: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class QuotaLedger:
    """In-memory per-UTC-day consumption counters, seeded from llm_requests."""

    def __init__(self) -> None:
        self._counter = _DayCounter(day=_today())

    def _roll(self) -> None:
        today = _today()
        if self._counter.day != today:
            self._counter = _DayCounter(day=today)

    def record(self, provenance: ProvenanceRecord) -> None:
        """on_provenance hook — count the CONCRETE serving provider."""
        if not provenance.success or not provenance.served_by_provider:
            return
        self._roll()
        p = provenance.served_by_provider
        self._counter.requests[p] = self._counter.requests.get(p, 0) + 1
        tokens = (provenance.input_tokens or 0) + (provenance.output_tokens or 0)
        if tokens:
            self._counter.tokens[p] = self._counter.tokens.get(p, 0) + tokens

    def seed(self, requests: dict[str, int], tokens: dict[str, int]) -> None:
        """Load today's already-persisted consumption (called once at startup)."""
        self._roll()
        for p, n in requests.items():
            self._counter.requests[p] = self._counter.requests.get(p, 0) + n
        for p, n in tokens.items():
            self._counter.tokens[p] = self._counter.tokens.get(p, 0) + n

    def used_today(self, provider: str) -> tuple[int, int]:
        self._roll()
        return (
            self._counter.requests.get(provider, 0),
            self._counter.tokens.get(provider, 0),
        )

    def remaining_fraction(self, provider: str) -> float:
        """1.0 = untouched/uncapped, 0.0 = a published cap is exhausted."""
        quota = PROVIDER_QUOTAS.get(provider, DEFAULT_QUOTA)
        reqs, toks = self.used_today(provider)
        fractions = [1.0]
        if quota.rpd:
            fractions.append(max(0.0, 1.0 - reqs / quota.rpd))
        if quota.tpd:
            fractions.append(max(0.0, 1.0 - toks / quota.tpd))
        return min(fractions)

    def snapshot(self) -> list[dict]:
        """Per-provider capacity view for the dashboard endpoint."""
        self._roll()
        providers = set(self._counter.requests) | set(PROVIDER_QUOTAS)
        rows = []
        for p in sorted(providers):
            quota = PROVIDER_QUOTAS.get(p, DEFAULT_QUOTA)
            reqs, toks = self.used_today(p)
            rows.append(
                {
                    "provider": p,
                    "requests_today": reqs,
                    "tokens_today": toks,
                    "requests_cap": quota.rpd,
                    "tokens_cap": quota.tpd,
                    "remaining_fraction": round(self.remaining_fraction(p), 4),
                    "note": quota.note,
                }
            )
        return rows


def quota_aware_ranker(ledger: QuotaLedger):
    """Ranker for PoolRouter: drain all quotas evenly — never hammer a capped
    provider while others sit idle. Stable sort preserves pool order as the
    tiebreak, and the local tier keeps its configured position."""

    def rank(entries):
        return sorted(
            entries,
            key=lambda e: -ledger.remaining_fraction(e[1].provider),
        )

    return rank
