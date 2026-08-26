"""add owner_id to businesses and personas (B6 Stage 1) and sync persona columns

Revision ID: 8d648b892fd3
Revises: e7f1a2b3c4d5
Create Date: 2026-08-26 16:16:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "8d648b892fd3"
down_revision: Union[str, Sequence[str], None] = "e7f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add owner_id to businesses
    op.add_column("businesses", sa.Column("owner_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_businesses_owner_id_users",
        "businesses",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_businesses_owner_id", "businesses", ["owner_id"])

    # 2. Add owner_id to personas
    op.add_column("personas", sa.Column("owner_id", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_personas_owner_id_users",
        "personas",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_personas_owner_id", "personas", ["owner_id"])

    # 3. Ensure sync columns on personas exist
    op.add_column("personas", sa.Column("tagline", sa.String(256), nullable=True))
    op.add_column(
        "personas",
        sa.Column("country_code", sa.String(16), nullable=True, server_default="BD"),
    )
    op.add_column(
        "personas",
        sa.Column(
            "personality",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "personas",
        sa.Column(
            "detailed_attributes",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("personas", "detailed_attributes")
    op.drop_column("personas", "personality")
    op.drop_column("personas", "country_code")
    op.drop_column("personas", "tagline")
    op.drop_index("ix_personas_owner_id", "personas")
    op.drop_constraint("fk_personas_owner_id_users", "personas", type_="foreignkey")
    op.drop_column("personas", "owner_id")
    op.drop_index("ix_businesses_owner_id", "businesses")
    op.drop_constraint("fk_businesses_owner_id_users", "businesses", type_="foreignkey")
    op.drop_column("businesses", "owner_id")
