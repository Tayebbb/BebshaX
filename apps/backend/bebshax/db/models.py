"""Declarative SQLAlchemy models for BebshaX.

All timestamps use datetime(timezone=True) with Python-side defaults to ensure
sqlite/postgres timezone consistency during testing.
"""

from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from bebshax.llm.adapters.embeddings import CANONICAL_DIM
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
    """Synthetic customer persona grounded in study segments, dataset distributions, and research evidence."""

    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    business_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("businesses.id"), nullable=True, index=True
    )
    study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    generation_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(
        String(64), default="ready"
    )  # ready, needs_review, draft, active, archived
    version: Mapped[int] = mapped_column(default=1)
    generation_model: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    archetype: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    demographics: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    goals: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    needs: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    pain_points: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    behaviors: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    preferences: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    motivations: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    objections: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    commercial_profile: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    technology_profile: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    evidence_citations: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    dataset_refs: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    grounding_score: Mapped[float] = mapped_column(Float, default=0.88)
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    validation_warnings: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    is_synthetic: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationship
    business: Mapped[Optional[Businesses]] = relationship("Businesses", back_populates="personas")


class Studies(Base):
    """Research study workflow state, questions, goal, and results."""

    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    type: Mapped[str] = mapped_column(String(64), default="interviews")
    goal: Mapped[str] = mapped_column(String(64), default="demand_validation")
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_audience: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pricing_hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="draft")  # draft, in_progress, completed, archived
    step: Mapped[int] = mapped_column(default=1)
    persona_count: Mapped[int] = mapped_column(default=0)
    persona_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    suggested_roles: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    script_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    findings: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(default=False)
    duration_text: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Copilot conversation history (list of {role, content, ...} dicts)
    copilot_messages: Mapped[Optional[list]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, default=None
    )
    # Generated persona objects from the workflow (list of persona dicts)
    personas_data: Mapped[Optional[list]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SavedAudiences(Base):
    """Reusable persona audience groups saved to the Persona Library."""

    __tablename__ = "saved_audiences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    personas_payload: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    role_distribution: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class DatasetSources(Base):
    """Dataset source metadata, profiled schema, statistics, and derived segments."""

    __tablename__ = "dataset_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), default="url")  # url, upload
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_file_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(64), default="csv")  # csv, json, xlsx, tsv
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="idle")  # idle, fetching, parsing, profiling, analyzing, ready, error
    row_count: Mapped[int] = mapped_column(default=0)
    column_count: Mapped[int] = mapped_column(default=0)
    schema_metadata: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    statistics: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    segments: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    persona_count_generated: Mapped[int] = mapped_column(default=0)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class DatasetPersonaRuns(Base):
    """Audit record for persona generation runs grounded in dataset distributions."""

    __tablename__ = "dataset_persona_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    model_used: Mapped[str] = mapped_column(String(256))
    requested_count: Mapped[int] = mapped_column(default=0)
    generated_count: Mapped[int] = mapped_column(default=0)
    valid_count: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    contradiction_count: Mapped[int] = mapped_column(default=0)
    distribution_target: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    distribution_actual: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    validation_results: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ResearchPlans(Base):
    """Structured research plan generated from the user's business idea."""

    __tablename__ = "research_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    business_idea: Mapped[str] = mapped_column(Text, nullable=False)
    target_market: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    problem_areas: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    behavioral_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    economic_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    competition_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    market_questions: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    dataset_requirements: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class DatasetCandidates(Base):
    """Discovered public dataset candidate before or after evaluation and import."""

    __tablename__ = "dataset_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    external_id: Mapped[str] = mapped_column(String(256))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    download_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    license: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    license_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(String(64), default="csv")
    size_bytes: Mapped[Optional[int]] = mapped_column(nullable=True)
    sample_rows: Mapped[Optional[int]] = mapped_column(nullable=True)
    sample_columns: Mapped[Optional[int]] = mapped_column(nullable=True)
    geographic_coverage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    population_coverage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    relevant_variables: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    relevance_score: Mapped[float] = mapped_column(Float, default=0.75)
    quality_score: Mapped[float] = mapped_column(Float, default=0.80)
    selection_status: Mapped[str] = mapped_column(
        String(64), default="discovered"
    )  # selected, discovered, rejected_by_user, import_failed, imported
    selection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_details: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    imported_dataset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ResearchRuns(Base):
    """Audit and lifecycle record for a study research execution."""

    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(64), default="pending")  # pending, understanding_idea, building_research_plan, searching_evidence, discovering_datasets, evaluating_datasets, importing_datasets, completed, failed
    query_count: Mapped[int] = mapped_column(default=0)
    source_count: Mapped[int] = mapped_column(default=0)
    claim_count: Mapped[int] = mapped_column(default=0)
    dataset_candidate_count: Mapped[int] = mapped_column(default=0)
    dataset_imported_count: Mapped[int] = mapped_column(default=0)
    current_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    step_progress: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    research_plan: Mapped[Optional[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    queries: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvidenceSources(Base):
    """External research sources discovered or uploaded for a study."""

    __tablename__ = "evidence_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="web")  # web, reddit, review, report, upload
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.8)
    status: Mapped[str] = mapped_column(String(64), default="processed")  # discovered, processed, failed
    metadata_payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class EvidenceChunks(Base):
    """Text chunks with pgvector embeddings for semantic retrieval."""

    __tablename__ = "evidence_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        JSON().with_variant(Vector(CANONICAL_DIM), "postgresql")
    )
    embedding_space: Mapped[str] = mapped_column(String(64), index=True)
    metadata_payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EvidenceClaims(Base):
    """Structured empirical claims extracted from evidence chunks with provenance."""

    __tablename__ = "evidence_claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="supported")  # supported, inference, unsupported
    category: Mapped[str] = mapped_column(String(64), default="general")  # problem, competition, pricing, behavior, complaints, general
    confidence: Mapped[float] = mapped_column(Float, default=0.75)
    supporting_source_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    supporting_chunk_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    contradicting_source_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SegmentationRuns(Base):
    """Audit and lifecycle record for a market segmentation run."""

    __tablename__ = "segmentation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(64), default="pending"
    )  # pending, analyzing_data, selecting_variables, clustering, evaluating_groups, interpreting_segments, completed, failed
    method: Mapped[str] = mapped_column(String(64), default="hybrid_quantile_clustering")
    configuration: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    dataset_versions: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    evidence_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    segment_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MarketSegments(Base):
    """Data-grounded customer market segments derived from datasets and evidence."""

    __tablename__ = "market_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    segmentation_run_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    cluster_label: Mapped[str] = mapped_column(String(64), default="cluster_0")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    population_count: Mapped[int] = mapped_column(default=0)
    population_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85)
    status: Mapped[str] = mapped_column(
        String(64), default="data_backed"
    )  # data_backed, inference_assisted, insufficient_evidence
    characteristics: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    variable_distributions: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    evidence_citations: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    differentiation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PersonaGenerationRuns(Base):
    """Audit and lifecycle record for a synthetic persona generation run."""

    __tablename__ = "persona_generation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    segmentation_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(64), default="pending"
    )  # pending, loading_segments, preparing_context, generating_personas, validating_personas, saving_personas, completed, failed
    configuration: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    target_count: Mapped[int] = mapped_column(default=0)
    generated_count: Mapped[int] = mapped_column(default=0)
    valid_count: Mapped[int] = mapped_column(default=0)
    warning_count: Mapped[int] = mapped_column(default=0)
    dataset_versions: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    evidence_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

