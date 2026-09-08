"""studies.script_meta provenance + drop the 'BD' default on personas.country_code

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-08 00:00:00.000000

Dynamic-output fixes (no pre-coded content track):

1. ``studies.script_meta`` (JSON, nullable) records the provenance of
   ``script_questions``: ``{source: "llm", served_by, llm_request_id,
   generated_at}``. NULL means "no generated script" — the template script
   path was removed, so there is nothing else it could mean.

2. ``personas.country_code`` loses its ``'BD'`` server default. A persona whose
   evidence never states a country must be stored with NULL, not silently
   placed in Bangladesh. Existing rows are left untouched: the value may be
   genuine, and rewriting history is not this migration's job.

Both steps are inspector-guarded so ``init_database()`` (create_all + stamp
head) stays a no-op path here.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_names = set(insp.get_table_names())

    if "studies" in table_names:
        columns = {c["name"] for c in insp.get_columns("studies")}
        if "script_meta" not in columns:
            op.add_column("studies", sa.Column("script_meta", JSON_TYPE, nullable=True))

    if "personas" in table_names:
        country = next(
            (c for c in insp.get_columns("personas") if c["name"] == "country_code"), None
        )
        if country is not None and country.get("default") is not None:
            # SQLite cannot ALTER a column default in place; the ORM never
            # relies on the server default, so only Postgres needs the fix.
            if bind.dialect.name == "postgresql":
                op.alter_column("personas", "country_code", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    table_names = set(insp.get_table_names())

    if "personas" in table_names and bind.dialect.name == "postgresql":
        op.alter_column("personas", "country_code", server_default="BD")

    if "studies" in table_names:
        columns = {c["name"] for c in insp.get_columns("studies")}
        if "script_meta" in columns:
            op.drop_column("studies", "script_meta")
