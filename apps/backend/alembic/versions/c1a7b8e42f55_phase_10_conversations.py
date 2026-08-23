"""Phase 10: conversations + conversation_turns tables.

Revision ID: c1a7b8e42f55
Revises: b9d4e5f60a17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1a7b8e42f55"
down_revision = "b9d4e5f60a17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_persona_id", "conversations", ["persona_id"])
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(64), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversation_turns_conversation_id", "conversation_turns", ["conversation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_turns_conversation_id", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_index("ix_conversations_persona_id", table_name="conversations")
    op.drop_table("conversations")
