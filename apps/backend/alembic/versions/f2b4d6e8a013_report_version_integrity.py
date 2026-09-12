"""Enforce positive, study-scoped report versions without rewriting history.

Revision ID: f2b4d6e8a013
Revises: e7a9c1d3f205
"""

import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


revision: str = "f2b4d6e8a013"
down_revision: str = "e7a9c1d3f205"
branch_labels: str | None = None
depends_on: str | None = None

UNIQUE_NAME = "uq_study_reports_study_version"
CHECK_NAME = "ck_study_reports_positive_version"
VERSION_CHECK = "version >= 1"


def _preflight(connection: Connection) -> tuple[bool, bool]:
    inspector = sa.inspect(connection)
    unique = next((
        constraint for constraint in inspector.get_unique_constraints("study_reports")
        if constraint["name"] == UNIQUE_NAME
    ), None)
    check = next((
        constraint for constraint in inspector.get_check_constraints("study_reports")
        if constraint["name"] == CHECK_NAME
    ), None)
    if unique is not None and unique["column_names"] != ["study_id", "version"]:
        raise RuntimeError("Existing report uniqueness constraint conflicts with migration; reconcile before upgrading")
    if check is not None and re.sub(r"[\s()]", "", check["sqltext"]).lower() != "version>=1":
        raise RuntimeError("Existing report version constraint conflicts with migration; reconcile before upgrading")
    if unique is None and any(index["name"] == UNIQUE_NAME for index in inspector.get_indexes("study_reports")):
        raise RuntimeError("Existing report index conflicts with migration; reconcile before upgrading")
    reports = sa.table("study_reports", sa.column("study_id"), sa.column("version"))
    duplicates = sa.select(sa.literal(1)).select_from(reports).group_by(
        reports.c.study_id, reports.c.version,
    ).having(sa.func.count() > 1).limit(1)
    invalid = sa.select(sa.literal(1)).select_from(reports).where(reports.c.version < 1).limit(1)
    if connection.execute(duplicates).first() is not None or connection.execute(invalid).first() is not None:
        raise RuntimeError("Report version history conflicts with constraints; retain rows and reconcile before upgrading")
    return unique is not None, check is not None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("LOCK TABLE study_reports IN SHARE ROW EXCLUSIVE MODE")
    has_unique, has_check = (False, False) if op.get_context().as_sql else _preflight(connection)
    if connection.dialect.name == "sqlite":
        if not has_unique or not has_check:
            with op.batch_alter_table("study_reports") as batch:
                if not has_unique:
                    batch.create_unique_constraint(UNIQUE_NAME, ["study_id", "version"])
                if not has_check:
                    batch.create_check_constraint(CHECK_NAME, VERSION_CHECK)
    else:
        if not has_unique:
            op.create_unique_constraint(UNIQUE_NAME, "study_reports", ["study_id", "version"])
        if not has_check:
            op.create_check_constraint(CHECK_NAME, "study_reports", VERSION_CHECK, postgresql_not_valid=True)
        if connection.dialect.name == "postgresql":
            op.execute(f"ALTER TABLE study_reports VALIDATE CONSTRAINT {CHECK_NAME}")


def downgrade() -> None:
    with op.batch_alter_table("study_reports") as batch:
        batch.drop_constraint(CHECK_NAME, type_="check")
        batch.drop_constraint(UNIQUE_NAME, type_="unique")