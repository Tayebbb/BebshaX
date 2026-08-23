"""Phase 8: persona_details, persona_attributes, persona_evidence tables.

Revision ID: a8f3c2d91e04
Revises: cb7c7deda755
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a8f3c2d91e04"
down_revision = "cb7c7deda755"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "persona_details",
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id"), primary_key=True),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("occupation", sa.String(256), nullable=False),
        sa.Column("location", sa.String(256), nullable=False),
        sa.Column("income_range", sa.String(128), nullable=False),
        sa.Column("education", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("warnings", _JSON, nullable=False, server_default="[]"),
    )
    op.create_table(
        "persona_attributes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("provenance_class", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_ids", _JSON, nullable=False, server_default="[]"),
    )
    op.create_index("ix_persona_attributes_persona_id", "persona_attributes", ["persona_id"])
    op.create_index("ix_persona_attributes_key", "persona_attributes", ["key"])
    op.create_table(
        "persona_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False, server_default="dataset_record"),
        sa.Column("relevance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_persona_evidence_persona_id", "persona_evidence", ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_persona_evidence_persona_id", table_name="persona_evidence")
    op.drop_table("persona_evidence")
    op.drop_index("ix_persona_attributes_key", table_name="persona_attributes")
    op.drop_index("ix_persona_attributes_persona_id", table_name="persona_attributes")
    op.drop_table("persona_attributes")
    op.drop_table("persona_details")
