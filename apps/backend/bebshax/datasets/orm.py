from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base, _utcnow


class DatasetVersions(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_sources.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    records_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_file_path: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    statistics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    segments: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)