"""Behavioral Testing & Simulation ORM — models for product/pricing/feature behavioral tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BehavioralTests(Base):
    """Behavioral test definition and configuration for a study."""

    __tablename__ = "behavioral_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_type: Mapped[str] = mapped_column(
        String(64), default="pricing_test", index=True
    )  # purchase_decision, pricing_test, feature_test, concept_test, message_test, offer_test, switching_test, objection_test
    configuration: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    status: Mapped[str] = mapped_column(
        String(32), default="ready"
    )  # draft, ready, running, completed, archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    @property
    def owner_id(self) -> str | None:
        return self.user_id


class BehavioralTestScenarios(Base):
    """Specific scenario and parameters bound to a behavioral test."""

    __tablename__ = "behavioral_test_scenarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    behavioral_test_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("behavioral_tests.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    scenario_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_parameters: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BehavioralTestRuns(Base):
    """Audit and lifecycle record for an execution run of a behavioral test."""

    __tablename__ = "behavioral_test_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    behavioral_test_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("behavioral_tests.id"), index=True
    )
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    execution_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_manifest: Mapped[Optional[dict]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    scenario_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenario_snapshot: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    target_population_type: Mapped[str] = mapped_column(
        String(64), default="all"
    )  # all, segment, selected_personas
    target_segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_persona_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    status: Mapped[str] = mapped_column(
        String(64), default="pending"
    )  # pending, running, completed, completed_with_warnings, failed, cancelled
    persona_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    aggregate_metrics: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    segment_analysis: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    cross_persona_patterns: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    risks: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    opportunities: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BehavioralTestResults(Base):
    """Detailed simulation response, probability, confidence, factors, and objections for one persona."""

    __tablename__ = "behavioral_test_results"
    __table_args__ = (UniqueConstraint("test_run_id", "persona_id", name="uq_behavioral_run_persona"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    test_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("behavioral_test_runs.id"), index=True
    )
    behavioral_test_id: Mapped[str] = mapped_column(String(64), index=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    persona_name: Mapped[str] = mapped_column(String(256))
    persona_version: Mapped[int] = mapped_column(Integer, default=1)
    segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    segment_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    decision: Mapped[str] = mapped_column(
        String(64)
    )  # strongly_positive, positive, neutral, negative, strongly_negative, likely_to_buy, might_buy, unlikely_to_buy, would_not_buy
    decision_label: Mapped[str] = mapped_column(String(128))
    probability: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[str] = mapped_column(String(32), default="low")  # low, medium, high
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    key_factors: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    motivators: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    objections: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    reasoning_summary: Mapped[str] = mapped_column(Text)
    simulation_context_sources: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    interview_signals_used: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    status: Mapped[str] = mapped_column(String(32), default="completed")  # completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provenance_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BehavioralInsights(Base):
    """Structured insights extracted from aggregate behavioral test runs."""

    __tablename__ = "behavioral_insights"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    test_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("behavioral_test_runs.id"), index=True
    )
    behavioral_test_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    type: Mapped[str] = mapped_column(
        String(64)
    )  # demand_signal, adoption_barrier, price_sensitivity, feature_appeal, messaging_signal, switching_trigger, objection, segment_difference, risk, opportunity
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    supporting_persona_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
