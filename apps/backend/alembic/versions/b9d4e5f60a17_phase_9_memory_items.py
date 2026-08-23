"""Phase 9: memory_items table with pgvector embedding + HNSW index.

Revision ID: b9d4e5f60a17
Revises: a8f3c2d91e04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "b9d4e5f60a17"
down_revision = "a8f3c2d91e04"
branch_labels = None
depends_on = None

_DIM = 384


def upgrade() -> None:
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON().with_variant(Vector(_DIM), "postgresql"), nullable=False),
        sa.Column("embedding_space", sa.String(64), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memory_items_persona_id", "memory_items", ["persona_id"])
    op.create_index("ix_memory_items_kind", "memory_items", ["kind"])
    op.create_index("ix_memory_items_embedding_space", "memory_items", ["embedding_space"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_memory_items_embedding_hnsw ON memory_items "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_memory_items_embedding_hnsw")
    op.drop_index("ix_memory_items_embedding_space", table_name="memory_items")
    op.drop_index("ix_memory_items_kind", table_name="memory_items")
    op.drop_index("ix_memory_items_persona_id", table_name="memory_items")
    op.drop_table("memory_items")
