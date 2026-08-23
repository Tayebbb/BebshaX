"""Phase-8 persona tables — additive to bebshax.db.models (Sazid's file stays
untouched; identity fields live in persona_details rather than altering the
personas skeleton). Registered on the shared Base metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PersonaDetails(Base):
    __tablename__ = "persona_details"

    persona_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("personas.id"), primary_key=True
    )
    age: Mapped[int] = mapped_column(Integer)
    occupation: Mapped[str] = mapped_column(String(256))
    location: Mapped[str] = mapped_column(String(256))
    income_range: Mapped[str] = mapped_column(String(128))
    education: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )


class PersonaAttributes(Base):
    __tablename__ = "persona_attributes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), ForeignKey("personas.id"), index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text)
    provenance_class: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=list
    )


class PersonaEvidence(Base):
    __tablename__ = "persona_evidence"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), ForeignKey("personas.id"), index=True)
    source: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(64), default="dataset_record")
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
