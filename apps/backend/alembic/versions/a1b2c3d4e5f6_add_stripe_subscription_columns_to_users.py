"""add stripe and subscription columns to users table

Revision ID: a1b2c3d4e5f6
Revises: 9f0a1b2c3d4e
Create Date: 2026-08-27 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9f0a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_users_stripe_customer_id"),
        "users",
        ["stripe_customer_id"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column("subscription_plan", sa.String(length=32), nullable=False, server_default="free"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "subscription_plan")
    op.drop_index(op.f("ix_users_stripe_customer_id"), table_name="users")
    op.drop_column("users", "stripe_customer_id")
