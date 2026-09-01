"""add saved_audiences table, restore HNSW index, fix confidence server defaults

Revision ID: d8e9f0a1b2c3
Revises: 9731ddaa8413
Create Date: 2026-09-02 00:00:00.000000

Covers three defects in one migration:

1. saved_audiences table was never created by any migration (ORM exists, create_all
   masked the gap). Fresh ``alembic upgrade head`` databases raise
   ``relation "saved_audiences" does not exist`` on the studies API.

2. ix_memory_items_embedding_hnsw was created by b9d4e5f60a17 and then dropped
   by 96ee206715d7 as an autogenerate artifact. The drop has been removed from
   96ee206715d7, but existing databases that already applied it have the index
   missing. This migration restores it idempotently.

3. Four confidence/confidence_score columns were given server_default='0.85' or
   '0.8' — fabricated scores that silently replace missing engine output at the
   DB layer. Reset to '0' following the precedent of b1c2d3e4f5a6.

Every step is idempotent. ``init_database()`` bootstraps empty databases with
``Base.metadata.create_all`` and stamps them at 9731ddaa8413, so an existing
database can already hold ``saved_audiences`` while sitting one revision behind
head. Unguarded DDL here would raise DuplicateTable and deadlock the startup
drift guard, which tells operators to run the very command that fails.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "9731ddaa8413"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    table_names = set(insp.get_table_names())
    # Read index names before any DDL so the inspector cache cannot go stale.
    existing_indexes: set[str] = (
        {ix["name"] for ix in insp.get_indexes("saved_audiences")}
        if "saved_audiences" in table_names
        else set()
    )

    # --- Defect 1: saved_audiences table (skipped when create_all already made it) ---
    if "saved_audiences" not in table_names:
        op.create_table(
            "saved_audiences",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("study_id", sa.String(length=64), nullable=True),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "persona_ids",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "personas_payload",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "role_distribution",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_audiences")),
        )

    if op.f("ix_saved_audiences_user_id") not in existing_indexes:
        op.create_index(
            op.f("ix_saved_audiences_user_id"), "saved_audiences", ["user_id"], unique=False
        )
    if op.f("ix_saved_audiences_study_id") not in existing_indexes:
        op.create_index(
            op.f("ix_saved_audiences_study_id"), "saved_audiences", ["study_id"], unique=False
        )

    # --- Defect 2: restore HNSW index dropped by the 96ee206715d7 autogenerate artifact ---
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_memory_items_embedding_hnsw "
            "ON memory_items USING hnsw (embedding vector_cosine_ops)"
        )

    # --- Defect 3: correct fabricated confidence server_defaults to 0 (SET DEFAULT is idempotent) ---
    op.alter_column("behavioral_insights", "confidence", server_default="0")
    op.alter_column("interview_insights", "confidence", server_default="0")
    op.alter_column("market_segments", "confidence_score", server_default="0")
    op.alter_column("behavioral_test_results", "confidence_score", server_default="0")


def downgrade() -> None:
    # Restore old confidence server_defaults
    op.alter_column("behavioral_test_results", "confidence_score", server_default="0.8")
    op.alter_column("market_segments", "confidence_score", server_default="0.85")
    op.alter_column("interview_insights", "confidence", server_default="0.85")
    op.alter_column("behavioral_insights", "confidence", server_default="0.85")

    # ix_memory_items_embedding_hnsw is deliberately NOT dropped: it is owned by
    # b9d4e5f60a17 and only re-asserted here, so dropping it would leave the
    # database worse off than before this revision ran.

    # Drop saved_audiences (guarded so downgrade is safe on any starting state)
    insp = sa.inspect(op.get_bind())
    if "saved_audiences" in insp.get_table_names():
        existing_indexes = {ix["name"] for ix in insp.get_indexes("saved_audiences")}
        if op.f("ix_saved_audiences_study_id") in existing_indexes:
            op.drop_index(op.f("ix_saved_audiences_study_id"), table_name="saved_audiences")
        if op.f("ix_saved_audiences_user_id") in existing_indexes:
            op.drop_index(op.f("ix_saved_audiences_user_id"), table_name="saved_audiences")
        op.drop_table("saved_audiences")
