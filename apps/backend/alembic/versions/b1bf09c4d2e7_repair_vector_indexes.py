"""Repair historical HNSW indexes omitted by create_all/stamp bootstraps.

Revision ID: b1bf09c4d2e7
Revises: a9c2e7b6d410
"""

from alembic import op


revision: str = "b1bf09c4d2e7"
down_revision: str = "a9c2e7b6d410"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name, index_name in (
        ("evidence_chunks", "ix_evidence_chunks_embedding_hnsw"),
        ("memory_items", "ix_memory_items_embedding_hnsw"),
    ):
        op.create_index(
            index_name,
            table_name,
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            if_not_exists=True,
        )


def downgrade() -> None:
    """Preserve indexes owned by the research and memory ancestor revisions."""