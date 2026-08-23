"""memory_items ORM — additive table on the shared Base (Phase 9).

The embedding column is pgvector Vector(384) on postgres and JSON on sqlite
(unit tests score in Python either way). `embedding_space` tags the vector's
space; retrieval never compares across spaces.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base
from bebshax.llm.adapters.embeddings import CANONICAL_DIM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryItems(Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), ForeignKey("personas.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # episodic|semantic|reflection
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(
        JSON().with_variant(Vector(CANONICAL_DIM), "postgresql")
    )
    embedding_space: Mapped[str] = mapped_column(String(64), index=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_accessed: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
