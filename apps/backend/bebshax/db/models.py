"""Declarative SQLAlchemy models for BebshaX.

All timestamps use datetime(timezone=True) with Python-side defaults to ensure
sqlite/postgres timezone consistency during testing.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bebshax.llm.failures import FailureKind
from bebshax.llm.types import TaskType


def _utcnow() -> datetime:
    """UTC now with timezone info."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base with naming convention (ix/uq/ck/fk/pk).

    This must be set BEFORE generating the first migration; it is effectively
    irreversible after. Enums use VARCHAR + CHECK (native_enum=False) so new
    members can be added without ALTER TYPE in production.
    """

    naming_convention = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


class LLMRequests(Base):
    """Per-request LLM provenance: provider, model, routing path, attempts,
    latency, tokens, failure/fallback reasons, final serving model.

    Attempts are stored as JSONB (postgres) / JSON (sqlite) to preserve the
    list of AttemptRecord objects without normalization. OTel semantic
    conventions used for column naming (request_model, response_model,
    input_tokens, output_tokens, provider_name).

    persona_id and conversation_id are nullable with NO foreign key constraint.
    Rationale: a provenance row must be writable for a persona that was never
    successfully created (i.e., generation failed). An FK would prevent
    logging the most important failures. Add comment for future maintainers.
    """

    __tablename__ = "llm_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task: Mapped[str] = mapped_column(Enum(TaskType, native_enum=False))
    pool: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    persona_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True, comment="nullable; no FK (failed generations must be loggable)"
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )

    # Routing + attempts
    routing_path: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    attempts: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list, comment="list of AttemptRecord as dict"
    )

    # Final serving model (OTel naming)
    served_by_provider: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    request_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    response_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Tokens + latency (OTel naming)
    input_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    total_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Outcome
    success: Mapped[bool] = mapped_column(default=False)

    # Optional: prompt/completion text (behind settings flag, never indexed)
    prompt_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completion_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_llm_requests_created_at_desc", created_at.desc()),
        Index("ix_llm_requests_provider_model", "served_by_provider", "request_model"),
    )


class ModelRegistry(Base):
    """Catalog of available LLM models with capability + health metadata.

    Currently a skeleton; registry sync jobs are unowned (later phase).
    Scores (quality, latency, health) are nullable; cooldown_until allows
    temporary removal due to 429/5xx.
    """

    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(128), index=True)
    model_name: Mapped[str] = mapped_column(String(256), index=True)
    enabled: Mapped[bool] = mapped_column(default=True)

    # Capabilities
    context_window: Mapped[Optional[int]] = mapped_column(nullable=True)
    supports_tools: Mapped[bool] = mapped_column(default=False)
    supports_json: Mapped[bool] = mapped_column(default=False)
    supports_vision: Mapped[bool] = mapped_column(default=False)
    reasoning_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Scoring (populated by Phase 11 evaluation + later registry sync)
    quality_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    latency_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    health_score: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Health tracking
    last_checked: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("uq_model_registry_provider_model", "provider_name", "model_name", unique=True),
    )


class Businesses(Base):
    """Business/product context for persona generation.

    Full business schema (industry, description, target_market, etc.)
    arrives in Phase 8 (persona engine). This is the skeleton.
    """

    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Relationship (lazy-loaded; populated in Phase 8)
    personas: Mapped[list["Personas"]] = relationship("Personas", back_populates="business")


class Personas(Base):
    """Synthetic persona skeleton.

    Full attribute schema (observed/inferred/synthetic provenance, persona
    details, memory hooks) arrives in Phase 8. This is the skeleton.

    persona_id is used in LLMRequests.persona_id (not as FK, to allow
    logging failed generations) and as a cross-table reference during
    interviews (Phase 10).
    """

    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[str] = mapped_column(String(64), ForeignKey("businesses.id"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(64), default="draft")  # draft, active, archived
    version: Mapped[int] = mapped_column(default=1)
    generation_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationship
    business: Mapped[Businesses] = relationship("Businesses", back_populates="personas")
