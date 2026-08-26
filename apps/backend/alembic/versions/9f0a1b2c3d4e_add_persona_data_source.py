"""add data_source to personas (H3 piece 2 — cached vs live labelling)

Revision ID: 9f0a1b2c3d4e
Revises: 4e5f6a7b8c9d
Create Date: 2026-08-27 03:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "9f0a1b2c3d4e"
down_revision: Union[str, Sequence[str], None] = "4e5f6a7b8c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing rows in the same statement. "live" is the
    # correct value for them: every persona in the table today was produced by an
    # inference pass, because the demo seeder is the only cached source and it
    # did not previously exist as a distinct category. The demo seeder writes
    # "cached" explicitly from now on.
    op.add_column(
        "personas",
        sa.Column(
            "data_source",
            sa.String(16),
            nullable=False,
            server_default="live",
        ),
    )


def downgrade() -> None:
    op.drop_column("personas", "data_source")
