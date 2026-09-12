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
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bebshax.llm.provenance import ProvenanceRecord, ProviderObservation
from bebshax.llm.service import Entry

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
    outcomes: dict[str, dict[str, int]] = field(default_factory=dict)
    recorded: set[str] = field(default_factory=set)
    reservations: dict[str, str] = field(default_factory=dict)


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

    def reserve_attempt(self, provider: str) -> str | None:
        self._roll()
        if self.remaining_fraction(provider) <= 0:
            return None
        reservation_id = uuid.uuid4().hex
        self._counter.reservations[reservation_id] = provider
        self._counter.requests[provider] = self._counter.requests.get(provider, 0) + 1
        counters = self._counter.outcomes.setdefault(provider, {})
        counters["attempted"] = counters.get("attempted", 0) + 1
        return reservation_id

    def record(self, provenance: ProvenanceRecord) -> None:
        """Count observed upstream attempts; cache hits and skips consume nothing."""
        self._roll()
        if provenance.request_id in self._counter.recorded:
            return
        self._counter.recorded.add(provenance.request_id)
        observed = False
        for attempt in provenance.attempts:
            if attempt.observations:
                for observation in attempt.observations:
                    self._record_observation(observation)
                observed = True
                continue
            cached = attempt.cached or "served from freellmpool response cache" in attempt.notes
            if cached:
                self._record_observation(ProviderObservation(provider=attempt.provider, requested_model=attempt.model, outcome="cached", consumption="none"))
                observed = True
            elif attempt.provider not in {"freellmpool", "unknown"}:
                self._record_observation(ProviderObservation(
                    provider=attempt.provider, requested_model=attempt.model,
                    outcome="succeeded" if attempt.success else "aborted" if "abort" in (attempt.failure_detail or "") else "failed",
                    consumption="known" if attempt.success else "unknown",
                    input_tokens=provenance.input_tokens if attempt.success else None,
                    output_tokens=provenance.output_tokens if attempt.success else None,
                ))
                observed = True
        if not observed and provenance.success and provenance.served_by_provider:
            self._record_observation(ProviderObservation(
                provider=provenance.served_by_provider, requested_model=provenance.served_by_model or "unknown",
                outcome="succeeded", consumption="known", input_tokens=provenance.input_tokens, output_tokens=provenance.output_tokens,
            ))

    def _record_observation(self, observation: ProviderObservation) -> None:
        provider = observation.provider
        counters = self._counter.outcomes.setdefault(provider, {})
        outcome = observation.outcome
        counters[outcome] = counters.get(outcome, 0) + 1
        if observation.consumption == "none" or outcome in {"cached", "skipped"}:
            return
        reserved = self._counter.reservations.pop(observation.account_reservation_id, None) == provider
        if not reserved:
            counters["attempted"] = counters.get("attempted", 0) + 1
            self._counter.requests[provider] = self._counter.requests.get(provider, 0) + 1
        if observation.consumption == "unknown":
            counters["unknown_consumption"] = counters.get("unknown_consumption", 0) + 1
        tokens = (observation.input_tokens or 0) + (observation.output_tokens or 0)
        self._counter.tokens[provider] = self._counter.tokens.get(provider, 0) + tokens

    def seed_provenance(self, records: Iterable[ProvenanceRecord]) -> None:
        self._roll()
        for record in records:
            if record.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d") == self._counter.day:
                self.record(record)

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
        providers = set(self._counter.requests) | set(self._counter.outcomes) | set(PROVIDER_QUOTAS)
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
                    **{f"{outcome}_today": self._counter.outcomes.get(p, {}).get(outcome, 0) for outcome in ("attempted", "succeeded", "failed", "cached", "aborted", "unknown_consumption")},
                }
            )
        return rows


# A capped provider is demoted only once it is nearly drained. Sorting on the
# continuous fraction would demote openrouter below the uncapped routes after a
# SINGLE request each day (49/50 < 1.0) — the opposite of "use free capacity".
QUOTA_DEMOTE_THRESHOLD = 0.15


def quota_aware_ranker(ledger: QuotaLedger) -> Callable[[list[Entry]], list[Entry]]:
    """Ranker for PoolRouter: bucketed demotion, otherwise configured order.

    Exhausted accounts are excluded. Near-empty accounts move behind healthy
    accounts within the tier supplied by PoolRouter, never across tiers.
    """

    def rank(entries: list[Entry]) -> list[Entry]:
        remote = [entry for entry in entries if ledger.remaining_fraction(entry[1].provider) > 0]
        fraction = {e[1].provider: ledger.remaining_fraction(e[1].provider) for e in remote}
        healthy = [e for e in remote if fraction[e[1].provider] >= QUOTA_DEMOTE_THRESHOLD]
        demoted = sorted(
            (e for e in remote if fraction[e[1].provider] < QUOTA_DEMOTE_THRESHOLD),
            key=lambda e: -fraction[e[1].provider],
        )
        return healthy + demoted

    return rank
