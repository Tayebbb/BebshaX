"""Reconcile the legacy hosted schema with the metadata the API validates at boot.

Revision ID: 1a3c5e7f9b2d
Revises: f2b4d6e8a013

The first hosted database predates Alembic ownership and was stamped rather than
migrated, so it drifted from the ORM in ways no revision corrected: three missing
``conversations`` indexes, a unique constraint plus a non-unique index on
``email_verification_tokens.token`` where the ORM declares one unique index,
fifteen nullable ``personas`` columns the ORM declares NOT NULL, and two
VARCHAR(16) columns the ORM widened to 32. Startup refuses any drift, so every
step here converges idempotently from either shape. Databases created from this
chain already match and are left untouched. Null persona attributes are backfilled
with the ORM's empty defaults; no row is deleted or renumbered.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Inspector


revision: str = "1a3c5e7f9b2d"
down_revision: str = "f2b4d6e8a013"
branch_labels: str | None = None
depends_on: str | None = None

CONVERSATION_INDEXES = (
    ("ix_conversations_study_id", "study_id"),
    ("ix_conversations_user_id", "user_id"),
    ("ix_conversations_generation_run_id", "generation_run_id"),
)
TOKEN_INDEX = "ix_email_verification_tokens_token"
# column -> SQL literal of the ORM default used to backfill NULLs before SET NOT NULL
PERSONA_JSON_DEFAULTS = {
    "demographics": "{}", "commercial_profile": "{}", "technology_profile": "{}",
    "goals": "[]", "needs": "[]", "pain_points": "[]", "behaviors": "[]", "preferences": "[]",
    "motivations": "[]", "objections": "[]", "evidence_citations": "[]", "dataset_refs": "[]",
    "validation_warnings": "[]",
}
PERSONA_FLOAT_COLUMNS = ("grounding_score", "confidence")
WIDENED_COLUMNS = (("conversation_turns", "role"), ("conversations", "status"))


def _column(inspector: Inspector, table: str, name: str) -> dict:
    return next(column for column in inspector.get_columns(table) if column["name"] == name)


def _json_literal(connection: Connection, value: str) -> str:
    return f"'{value}'::jsonb" if connection.dialect.name == "postgresql" else f"'{value}'"


def _upgrade_online(connection: Connection) -> None:
    inspector = sa.inspect(connection)

    existing = {index["name"] for index in inspector.get_indexes("conversations")}
    for name, column in CONVERSATION_INDEXES:
        if name not in existing:
            op.create_index(name, "conversations", [column])

    token_uniques = [
        constraint["name"] for constraint in inspector.get_unique_constraints("email_verification_tokens")
        if constraint["column_names"] == ["token"] and constraint["name"]
    ]
    token_index = next((index for index in inspector.get_indexes("email_verification_tokens") if index["name"] == TOKEN_INDEX), None)
    if token_uniques or token_index is None or not token_index["unique"]:
        with op.batch_alter_table("email_verification_tokens") as batch:
            for constraint in token_uniques:
                batch.drop_constraint(constraint, type_="unique")
            if token_index is not None:
                batch.drop_index(TOKEN_INDEX)
            batch.create_index(TOKEN_INDEX, ["token"], unique=True)

    nullable = {name for name in (*PERSONA_JSON_DEFAULTS, *PERSONA_FLOAT_COLUMNS) if _column(inspector, "personas", name)["nullable"]}
    if nullable:
        for name in nullable:
            default = _json_literal(connection, PERSONA_JSON_DEFAULTS[name]) if name in PERSONA_JSON_DEFAULTS else "0.0"
            op.execute(sa.text(f"UPDATE personas SET {name} = {default} WHERE {name} IS NULL"))
        with op.batch_alter_table("personas") as batch:
            for name in nullable:
                batch.alter_column(name, existing_type=_column(inspector, "personas", name)["type"], nullable=False)

    for table, name in WIDENED_COLUMNS:
        current = _column(inspector, table, name)
        if getattr(current["type"], "length", None) is not None and current["type"].length < 32:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(name, existing_type=current["type"], type_=sa.String(32),
                                   existing_nullable=current["nullable"], existing_server_default=current.get("default"))


def _upgrade_offline() -> None:
    """PostgreSQL-only SQL script: every statement tolerates both legacy and chain shapes."""
    for name, column in CONVERSATION_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON conversations ({column})")
    op.execute("ALTER TABLE email_verification_tokens DROP CONSTRAINT IF EXISTS email_verification_tokens_token_key")
    op.execute(f"DROP INDEX IF EXISTS {TOKEN_INDEX}")
    op.execute(f"CREATE UNIQUE INDEX {TOKEN_INDEX} ON email_verification_tokens (token)")
    for name, literal in PERSONA_JSON_DEFAULTS.items():
        op.execute(f"UPDATE personas SET {name} = '{literal}'::jsonb WHERE {name} IS NULL")
        op.execute(f"ALTER TABLE personas ALTER COLUMN {name} SET NOT NULL")
    for name in PERSONA_FLOAT_COLUMNS:
        op.execute(f"UPDATE personas SET {name} = 0.0 WHERE {name} IS NULL")
        op.execute(f"ALTER TABLE personas ALTER COLUMN {name} SET NOT NULL")
    for table, name in WIDENED_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {name} TYPE VARCHAR(32)")


def upgrade() -> None:
    if op.get_context().as_sql:
        _upgrade_offline()
    else:
        _upgrade_online(op.get_bind())


def downgrade() -> None:
    """Converging revision: the chain schema was already in this shape, so there is nothing to undo."""
