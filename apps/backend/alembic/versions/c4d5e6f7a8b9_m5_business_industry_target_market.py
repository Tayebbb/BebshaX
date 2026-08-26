"""M5: businesses.industry / target_market become real columns.

Legacy rows stuffed these into description as "Industry: X | Target Market: Y\n\n<desc>".
The upgrade migrates that data out and strips the header. Downgrade drops the
columns (header form is not reconstructed).

Revision ID: c4d5e6f7a8b9
Revises: e7f1a2b3c4d5
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "e7f1a2b3c4d5"
branch_labels = None
depends_on = None


def _split_legacy_header(description: str) -> tuple[str | None, str | None, str]:
    """Parse the exact header format the old endpoint wrote. Anything else is user content.

    Guards:
    - every " | " segment must be a recognized field;
    - extracted values must fit the old BusinessCreate bound (256 chars) —
      anything longer provably is not legacy writer output.
    Residual ambiguity (documented): a short pipe-less "Industry: X" IS treated
    as legacy, because industry-only creates wrote exactly that form. A
    recognized-but-empty header ("Industry: \n\n…") is left untouched —
    near-unreachable since the old writer required truthy input.
    """
    industry, target_market = None, None
    parts = description.split("\n\n", 1)
    header, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    fields = header.split(" | ")
    recognized = []
    for field in fields:
        if field.startswith("Industry: "):
            value = field[len("Industry: "):].strip() or None
            if value is not None and len(value) > 256:
                return None, None, description  # not legacy — user content
            industry = value
            recognized.append(field)
        elif field.startswith("Target Market: "):
            value = field[len("Target Market: "):].strip() or None
            if value is not None and len(value) > 256:
                return None, None, description
            target_market = value
            recognized.append(field)
    if len(recognized) != len(fields):
        # Header line contains unrecognized segments — treat the whole
        # description as user content (the corruption case the audit found).
        return None, None, description
    return industry, target_market, rest


def upgrade() -> None:
    op.add_column("businesses", sa.Column("industry", sa.String(256), nullable=True))
    op.add_column("businesses", sa.Column("target_market", sa.String(256), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, description FROM businesses "
            "WHERE description LIKE 'Industry: %' OR description LIKE 'Target Market: %'"
        )
    ).fetchall()
    for row in rows:
        industry, target_market, clean_desc = _split_legacy_header(row.description or "")
        if industry is None and target_market is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE businesses SET industry = :ind, target_market = :tm, description = :d "
                "WHERE id = :id"
            ),
            {"ind": industry, "tm": target_market, "d": clean_desc, "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("businesses", "target_market")
    op.drop_column("businesses", "industry")
