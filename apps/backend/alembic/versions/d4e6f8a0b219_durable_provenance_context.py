"""Retain request-time processing context in durable provenance.

Revision ID: d4e6f8a0b219
Revises: c6f8a2d4e901
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e6f8a0b219"
down_revision: str = "c6f8a2d4e901"
branch_labels: str | None = None
depends_on: str | None = None

CLASSIFICATION_CHECK = "data_classification IN ('synthetic', 'private', 'unknown')"


def _added_columns() -> tuple[tuple[str, sa.Column], ...]:
    return (
        ("llm_requests", sa.Column("study_id", sa.String(64), nullable=True)),
        ("llm_requests", sa.Column("data_classification", sa.String(16), nullable=False, server_default="unknown")),
        ("llm_requests", sa.Column("processing_policy_id", sa.Text(), nullable=True)),
        ("llm_requests", sa.Column(
            "processing_provider_allowlist", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False, server_default="[]",
        )),
        ("llm_requests", sa.Column(
            "processing_openrouter_upstreams", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False, server_default="[]",
        )),
        ("llm_requests", sa.Column("estimated_tokens", sa.Integer(), nullable=True)),
    )


def upgrade() -> None:
    bind = op.get_bind()
    offline = op.get_context().as_sql
    existing = {} if offline else {
        column["name"]: column for column in sa.inspect(bind).get_columns("llm_requests")
    }
    columns = _added_columns()
    for _, column in columns:
        actual = existing.get(column.name)
        if actual is not None and (
            actual["nullable"] != column.nullable
            or str(actual["type"].compile(dialect=bind.dialect)) != str(column.type.compile(dialect=bind.dialect))
        ):
            raise RuntimeError("Existing provenance context column conflicts with migration; reconcile before upgrading")
    for table_name, column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)

    constraint_name = "ck_llm_requests_data_classification"
    checks = set() if offline else {
        constraint["name"] for constraint in sa.inspect(bind).get_check_constraints("llm_requests")
    }
    if constraint_name not in checks:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("llm_requests") as batch:
                batch.create_check_constraint(constraint_name, CLASSIFICATION_CHECK)
        else:
            op.create_check_constraint(
                constraint_name, "llm_requests", CLASSIFICATION_CHECK, postgresql_not_valid=True,
            )
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TABLE llm_requests VALIDATE CONSTRAINT {constraint_name}")


def downgrade() -> None:
    raise RuntimeError("Automatic downgrade would discard provenance processing context; use a reviewed restore plan")