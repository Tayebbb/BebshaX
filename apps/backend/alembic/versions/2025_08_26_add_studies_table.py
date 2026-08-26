"""Add Studies table (missing from earlier migrations)

Revision ID: 2025_08_26_001
Revises: 96ee206715d7
Create Date: 2026-08-26 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '2025_08_26_001'
down_revision: Union[str, Sequence[str], None] = '33b91ce44e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create studies table."""
    op.create_table('studies',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=256), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False, server_default='interviews'),
    sa.Column('goal', sa.String(length=64), nullable=False, server_default='demand_validation'),
    sa.Column('prompt', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=64), nullable=False, server_default='draft'),
    sa.Column('step', sa.Integer(), nullable=False, server_default='1'),
    sa.Column('persona_count', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('persona_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
    sa.Column('suggested_roles', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
    sa.Column('script_questions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
    sa.Column('findings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('is_demo', sa.Boolean(), nullable=False, server_default='false'),
    sa.Column('duration_text', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_studies_user_id'), 'studies', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema - drop studies table."""
    op.drop_index(op.f('ix_studies_user_id'), table_name='studies')
    op.drop_table('studies')
