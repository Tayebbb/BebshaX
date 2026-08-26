"""merge owner_id and business metadata heads

Revision ID: 30292b0ed8b8
Revises: 8d648b892fd3, c4d5e6f7a8b9
Create Date: 2026-08-26 17:20:48.590277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30292b0ed8b8'
down_revision: Union[str, Sequence[str], None] = ('8d648b892fd3', 'c4d5e6f7a8b9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
