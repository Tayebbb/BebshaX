"""add content_hash to dataset_sources

Revision ID: 614fe05a6f4d
Revises: f5e32fddb1b9
Create Date: 2026-08-26 00:47:45.884075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '614fe05a6f4d'
down_revision: Union[str, Sequence[str], None] = 'f5e32fddb1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('dataset_sources', sa.Column('content_hash', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dataset_sources', 'content_hash')
