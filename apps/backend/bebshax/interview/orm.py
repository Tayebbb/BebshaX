"""Conversation ORM — additive tables on the shared Base (Phase 10)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Conversations(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), ForeignKey("personas.id"), index=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ConversationTurns(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.id"), index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # interviewer|persona
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
