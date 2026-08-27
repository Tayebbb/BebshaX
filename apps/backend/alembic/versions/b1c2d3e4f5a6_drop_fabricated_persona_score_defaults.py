"""drop fabricated persona score server defaults (research-integrity hardening)

Revision ID: b1c2d3e4f5a6
Revises: 9f0a1b2c3d4e
Create Date: 2026-08-28

``personas.grounding_score``/``confidence`` shipped with server defaults of
0.88/0.85 — any insert path that omitted them fabricated a high score at the
database layer. Grounding is now measured (OBSERVED claims / total claims), so
the default must be honest zero. Existing rows are NOT rewritten: their scores
were produced by the old application code and remain part of the audit trail.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "9f0a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("personas", "grounding_score", server_default="0")
    op.alter_column("personas", "confidence", server_default="0")


def downgrade() -> None:
    op.alter_column("personas", "grounding_score", server_default="0.88")
    op.alter_column("personas", "confidence", server_default="0.85")
