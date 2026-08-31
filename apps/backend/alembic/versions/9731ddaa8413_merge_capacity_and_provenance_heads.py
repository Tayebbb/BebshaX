"""merge capacity and provenance heads

Revision ID: 9731ddaa8413
Revises: a1b2c3d4e5f6, b1c2d3e4f5a6
Create Date: 2026-08-31 15:30:55.407519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9731ddaa8413'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'b1c2d3e4f5a6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
