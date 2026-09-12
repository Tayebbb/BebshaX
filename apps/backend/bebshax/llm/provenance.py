"""Per-request provenance records: every LLM request must be fully traceable
(provider, model, routing path, attempts, latency, tokens, failure/fallback
reasons, final serving model). Persisted to the `llm_requests` table in Phase 6.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from bebshax.llm.failures import FailureKind


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProviderObservation(BaseModel):
    provider: str
    requested_model: str
    account_reservation_id: str | None = None
    reported_model: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    latency_ms: float | None = None
    outcome: Literal["succeeded", "failed", "aborted", "unknown", "skipped", "cached"] = "unknown"
    consumption: Literal["known", "unknown", "none"] = "unknown"
    status_code: int | None = None
    failure_kind: FailureKind | None = None
    retry_after_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None


class AttemptRecord(BaseModel):
    attempt_number: int
    provider: str
    model: str
    started_at: datetime = Field(default_factory=_utcnow)
    latency_ms: float | None = None
    success: bool = False
    failure_kind: FailureKind | None = None
    failure_detail: str | None = None
    fallback_reason: str | None = None  # why the router moved past this attempt
    notes: list[str] = Field(default_factory=list)  # adapter-internal detail (e.g. inner failovers)
    # Routing candidate that produced the answer when it differs from the
    # concrete serving route, e.g. "freellmpool/auto" when llm7/codestral served.
    via: str | None = None
    elapsed_ms: float | None = None
    cached: bool = False
    observations: list[ProviderObservation] = Field(default_factory=list)


class ProvenanceRecord(BaseModel):
    request_id: str
    task: str
    pool: str | None = None
    persona_id: str | None = None
    conversation_id: str | None = None
    owner_user_id: str | None = Field(default=None, frozen=True)
    study_id: str | None = Field(default=None, frozen=True)
    data_classification: Literal["synthetic", "private", "unknown"] = Field(default="unknown", frozen=True)
    processing_policy_id: str | None = Field(default=None, frozen=True)
    processing_provider_allowlist: tuple[str, ...] = Field(default=(), frozen=True)
    processing_openrouter_upstreams: tuple[str, ...] = Field(default=(), frozen=True)
    created_at: datetime = Field(default_factory=_utcnow)
    routing_path: list[str] = Field(default_factory=list)  # ordered candidates considered
    attempts: list[AttemptRecord] = Field(default_factory=list)
    estimated_tokens: int | None = None  # pre-flight estimate that drove eligibility
    served_by_provider: str | None = None
    served_by_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_latency_ms: float | None = None
    success: bool = False
    persistence_status: Literal["not_requested", "submitted", "acknowledged", "failed", "unknown"] = "not_requested"
