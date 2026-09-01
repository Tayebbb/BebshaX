"""backfill owner_id via tagged system account and enforce NOT NULL on businesses and personas

Revision ID: 4e5f6a7b8c9d
Revises: 7a8b9c0d1e2f
Create Date: 2026-08-26 23:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4e5f6a7b8c9d"
down_revision: Union[str, None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure tagged system holder account exists for demo/system ownership
    system_user_id = "usr_system_holder"
    op.execute(
        sa.text(
            "INSERT INTO users (id, email, full_name, auth_provider, is_active, is_verified, created_at, updated_at)"
            " VALUES (:id, 'system@bebshax.internal', 'BebshaX System Data (do not treat as a real user)', 'system', true, true, now(), now())"
            " ON CONFLICT (id) DO NOTHING"
        ).bindparams(id=system_user_id)
    )

    # 2. Backfill existing orphaned rows to the tagged system holder account
    op.execute(
        sa.text("UPDATE businesses SET owner_id = :uid WHERE owner_id IS NULL").bindparams(uid=system_user_id)
    )
    op.execute(
        sa.text("UPDATE personas SET owner_id = :uid WHERE owner_id IS NULL").bindparams(uid=system_user_id)
    )

    # 3. Enforce NOT NULL on businesses and personas
    op.alter_column("businesses", "owner_id", nullable=False)
    op.alter_column("personas", "owner_id", nullable=False)


def downgrade() -> None:
    op.alter_column("personas", "owner_id", nullable=True)
    op.alter_column("businesses", "owner_id", nullable=True)
