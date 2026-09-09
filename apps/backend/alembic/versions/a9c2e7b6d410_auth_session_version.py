"""Add a revocable session version to existing user accounts.

Revision ID: a9c2e7b6d410
Revises: f2a3b4c5d6e7
"""

from alembic import op
import sqlalchemy as sa


revision: str = "a9c2e7b6d410"
down_revision: str = "f2a3b4c5d6e7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    if not op.get_context().as_sql:
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
        if "session_version" in columns:
            return
    op.add_column(
        "users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql:
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
        if "session_version" not in columns:
            return
    op.drop_column("users", "session_version")