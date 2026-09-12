"""Immutable persona snapshots, erased only with their owning persona."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from bebshax.db.models import Base, _utcnow


class PersonaVersions(Base):
    __tablename__ = "persona_versions"

    persona_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("personas.id", ondelete="CASCADE"), primary_key=True,
    )
    version: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    study_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    legacy_profile: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True,
    )
    capture_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("persona_id", "version", "owner_id", name="uq_persona_versions_identity_owner"),
        CheckConstraint("version >= 1", name="ck_persona_versions_positive_version"),
        CheckConstraint("capture_kind IN ('generated', 'observed_current')", name="ck_persona_versions_capture_kind"),
        Index("ix_persona_versions_owner_persona", "owner_id", "persona_id"),
    )


class PersonaSourceSelections(Base):
    __tablename__ = "persona_source_selections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", name="fk_source_selection_owner", ondelete="RESTRICT"), nullable=False,
    )
    scope_owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False)
    persona_version: Mapped[int] = mapped_column(nullable=False)
    persona_owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    study_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_namespace: Mapped[str] = mapped_column(String(256), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["persona_id", "persona_version", "persona_owner_id"],
            ["persona_versions.persona_id", "persona_versions.version", "persona_versions.owner_id"],
            name="fk_source_selection_version_owner", ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["study_id", "scope_owner_id"], ["studies.id", "studies.user_id"],
            name="fk_source_selection_study_owner", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["business_id", "scope_owner_id"], ["businesses.id", "businesses.owner_id"],
            name="fk_source_selection_business_owner", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["dataset_id", "scope_owner_id"], ["dataset_sources.id", "dataset_sources.user_id"],
            name="fk_source_selection_dataset_owner", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(CASE WHEN study_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN business_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN dataset_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_source_selection_one_scope",
        ),
        CheckConstraint(
            "length(trim(owner_id)) > 0 AND owner_id NOT IN ('usr_system_holder', 'usr_default', 'anonymous')",
            name="ck_source_selection_private_owner",
        ),
        CheckConstraint(
            "scope_owner_id = owner_id OR (study_id IS NULL AND "
            "scope_owner_id IN ('usr_system_holder', 'usr_default', 'anonymous'))",
            name="ck_source_selection_scope_owner",
        ),
        CheckConstraint(
            "persona_owner_id = owner_id OR persona_owner_id IN ('usr_system_holder', 'usr_default', 'anonymous')",
            name="ck_source_selection_persona_owner",
        ),
        CheckConstraint(
            "length(trim(source_namespace)) > 0 AND length(trim(source_record_id)) > 0",
            name="ck_source_selection_identity",
        ),
        CheckConstraint("released_at IS NULL OR released_at >= created_at", name="ck_source_selection_release_time"),
        Index("ix_source_selections_persona_version", "persona_id", "persona_version"),
        Index(
            "uq_source_active_study", "owner_id", "study_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=text("released_at IS NULL AND study_id IS NOT NULL"),
            sqlite_where=text("released_at IS NULL AND study_id IS NOT NULL"),
        ),
        Index(
            "uq_source_active_business", "owner_id", "business_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=text("released_at IS NULL AND business_id IS NOT NULL"),
            sqlite_where=text("released_at IS NULL AND business_id IS NOT NULL"),
        ),
        Index(
            "uq_source_active_dataset", "owner_id", "dataset_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=text("released_at IS NULL AND dataset_id IS NOT NULL"),
            sqlite_where=text("released_at IS NULL AND dataset_id IS NOT NULL"),
        ),
    )


@event.listens_for(PersonaVersions, "before_update")
def _prevent_snapshot_update(mapper: Mapper, connection: Connection, target: PersonaVersions) -> None:
    raise ValueError("Persona version snapshots are immutable.")