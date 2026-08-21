"""Per-request provenance records: every LLM request must be fully traceable
(provider, model, routing path, attempts, latency, tokens, failure/fallback
reasons, final serving model). Persisted to the `llm_requests` table in Phase 6.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from bebshax.llm.failures import FailureKind


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


class ProvenanceRecord(BaseModel):
    request_id: str
    task: str
    pool: str | None = None
    persona_id: str | None = None
    conversation_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    routing_path: list[str] = Field(default_factory=list)  # ordered candidates considered
    attempts: list[AttemptRecord] = Field(default_factory=list)
    served_by_provider: str | None = None
    served_by_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_latency_ms: float | None = None
    success: bool = False
