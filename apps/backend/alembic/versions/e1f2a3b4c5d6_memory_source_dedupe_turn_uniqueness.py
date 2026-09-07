"""memory_items source/conversation_id/content_hash + unique conversation turn numbers

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-09-06 00:00:00.000000

Red-team fixes (persona/interview/memory track):

1. memory_items gains ``source`` (persona | interviewer | system, NOT NULL,
   default 'persona'), ``conversation_id`` and ``content_hash`` (sha256 of
   kind+text, dedupe key). Existing rows were all written by the persona
   write-back, so the server default is the truthful backfill.

2. conversation_turns gets UNIQUE (conversation_id, turn_number). Concurrent
   ask() calls used to compute the turn number before the LLM call and persist
   duplicates. Rows already carrying duplicate numbers are renumbered
   chronologically (created_at, id) per conversation BEFORE the constraint is
   created, and conversations.turn_count is re-derived from the same count.

Every step is inspector-guarded: ``init_database()`` bootstraps fresh databases
with ``Base.metadata.create_all`` (which already includes these columns and the
constraint) and stamps them at head, so this migration must be a no-op there
rather than fail with DuplicateColumn/DuplicateObject.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TURN_UNIQUE = "uq_conversation_turns_conversation_turn"
IX_CONVERSATION = "ix_memory_items_conversation_id"
IX_HASH = "ix_memory_items_content_hash"


def _renumber_duplicate_turns(bind) -> None:
    """Give every turn of a conversation with duplicate numbers a fresh 1..n
    sequence in chronological order so the UNIQUE constraint can be added."""
    dup_rows = bind.execute(
        sa.text(
            "SELECT DISTINCT conversation_id FROM conversation_turns "
            "GROUP BY conversation_id, turn_number HAVING COUNT(*) > 1"
        )
    ).fetchall()
    for (conversation_id,) in dup_rows:
        turns = bind.execute(
            sa.text(
                "SELECT id FROM conversation_turns WHERE conversation_id = :cid "
                "ORDER BY turn_number, created_at, id"
            ),
            {"cid": conversation_id},
        ).fetchall()
        for number, (turn_id,) in enumerate(turns, start=1):
            bind.execute(
                sa.text("UPDATE conversation_turns SET turn_number = :n WHERE id = :id"),
                {"n": number, "id": turn_id},
            )
        bind.execute(
            sa.text("UPDATE conversations SET turn_count = :n WHERE id = :cid"),
            {"n": len(turns), "cid": conversation_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_names = set(insp.get_table_names())

    # --- 1. memory_items provenance columns -------------------------------
    if "memory_items" in table_names:
        columns = {c["name"] for c in insp.get_columns("memory_items")}
        indexes = {ix["name"] for ix in insp.get_indexes("memory_items")}
        if "source" not in columns:
            op.add_column(
                "memory_items",
                sa.Column("source", sa.String(length=16), nullable=False, server_default="persona"),
            )
        if "conversation_id" not in columns:
            op.add_column(
                "memory_items", sa.Column("conversation_id", sa.String(length=64), nullable=True)
            )
        if "content_hash" not in columns:
            op.add_column(
                "memory_items", sa.Column("content_hash", sa.String(length=64), nullable=True)
            )
        if op.f(IX_CONVERSATION) not in indexes:
            op.create_index(op.f(IX_CONVERSATION), "memory_items", ["conversation_id"], unique=False)
        if op.f(IX_HASH) not in indexes:
            op.create_index(op.f(IX_HASH), "memory_items", ["content_hash"], unique=False)

    # --- 2. unique (conversation_id, turn_number) --------------------------
    if "conversation_turns" in table_names:
        uniques = {uc["name"] for uc in insp.get_unique_constraints("conversation_turns")}
        # sqlite reports UNIQUE constraints created by create_all as indexes too
        uniques |= {ix["name"] for ix in insp.get_indexes("conversation_turns") if ix.get("unique")}
        if TURN_UNIQUE not in uniques:
            _renumber_duplicate_turns(bind)
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("conversation_turns") as batch:
                    batch.create_unique_constraint(TURN_UNIQUE, ["conversation_id", "turn_number"])
            else:
                op.create_unique_constraint(
                    TURN_UNIQUE, "conversation_turns", ["conversation_id", "turn_number"]
                )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_names = set(insp.get_table_names())

    if "conversation_turns" in table_names:
        uniques = {uc["name"] for uc in insp.get_unique_constraints("conversation_turns")}
        uniques |= {ix["name"] for ix in insp.get_indexes("conversation_turns") if ix.get("unique")}
        if TURN_UNIQUE in uniques:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("conversation_turns") as batch:
                    batch.drop_constraint(TURN_UNIQUE, type_="unique")
            else:
                op.drop_constraint(TURN_UNIQUE, "conversation_turns", type_="unique")
        # Renumbered turns are left as-is: they are now correct chronology.

    if "memory_items" in table_names:
        columns = {c["name"] for c in insp.get_columns("memory_items")}
        indexes = {ix["name"] for ix in insp.get_indexes("memory_items")}
        if op.f(IX_HASH) in indexes:
            op.drop_index(op.f(IX_HASH), table_name="memory_items")
        if op.f(IX_CONVERSATION) in indexes:
            op.drop_index(op.f(IX_CONVERSATION), table_name="memory_items")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("memory_items") as batch:
                for name in ("content_hash", "conversation_id", "source"):
                    if name in columns:
                        batch.drop_column(name)
        else:
            for name in ("content_hash", "conversation_id", "source"):
                if name in columns:
                    op.drop_column("memory_items", name)
