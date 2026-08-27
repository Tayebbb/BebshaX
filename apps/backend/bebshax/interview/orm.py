"""Conversation / Interview ORM — models for adaptive persona interviews and insights."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversations(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    study_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    persona_id: Mapped[str] = mapped_column(String(64), ForeignKey("personas.id"), index=True)
    persona_version: Mapped[int] = mapped_column(Integer, default=1)
    generation_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    objective: Mapped[str] = mapped_column(Text)
    custom_objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interview_type: Mapped[str] = mapped_column(String(64), default="adaptive_persona")
    length_tier: Mapped[str] = mapped_column(String(32), default="standard")  # short, standard, deep
    max_turns: Mapped[int] = mapped_column(Integer, default=14)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active, completed, archived
    topics_explored: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_findings: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    structured_insights: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    configuration: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# Alias Interviews for semantic clarity in Part 6
Interviews = Conversations


class ConversationTurns(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id"), index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(32))  # researcher, persona, system, interviewer
    content: Mapped[str] = mapped_column(Text)
    topic: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    served_by: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    retrieved_memories: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# Alias InterviewTurns
InterviewTurns = ConversationTurns


class InterviewInsights(Base):
    __tablename__ = "interview_insights"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interview_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id"), index=True
    )
    study_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(64))  # pain_point, need, motivation, behavior, objection, feature, pricing, decision_factor, unresolved_question
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    supporting_turn_numbers: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 = unmeasured, never an invented default
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
