"""Legacy hosted-schema reconciliation: converge without touching chain databases or rows."""

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection


REVISION = "1a3c5e7f9b2d"
PREDECESSOR = "f2b4d6e8a013"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"
PERSONA_JSON = ("demographics", "goals", "needs", "pain_points", "behaviors", "preferences", "motivations",
                "objections", "commercial_profile", "technology_profile", "evidence_citations", "dataset_refs",
                "validation_warnings")
PERSONA_FLOATS = ("grounding_score", "confidence")


@pytest.fixture
def reconcile_revision() -> ModuleType:
    path = SCRIPT_PATH / "versions" / f"{REVISION}_reconcile_legacy_hosted_schema.py"
    assert path.is_file(), "The hosted schema drift requires a forward reconciliation migration"
    return ScriptDirectory(str(SCRIPT_PATH)).get_revision(REVISION).module


def _legacy_tables(metadata: sa.MetaData) -> None:
    """The stamped production shape: nullable persona attributes, no conversation indexes,
    a unique constraint plus non-unique index on the token, and VARCHAR(16) statuses."""
    sa.Table(
        "personas", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        *[sa.Column(name, sa.JSON(), nullable=True) for name in PERSONA_JSON],
        *[sa.Column(name, sa.Float(), nullable=True) for name in PERSONA_FLOATS],
    )
    sa.Table(
        "conversations", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("study_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("generation_run_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    )
    sa.Table(
        "conversation_turns", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
    )
    sa.Table(
        "email_verification_tokens", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.UniqueConstraint("token", name="email_verification_tokens_token_key"),
        sa.Index("ix_email_verification_tokens_token", "token"),
    )


@pytest.fixture
def legacy_connection(monkeypatch: pytest.MonkeyPatch, reconcile_revision: ModuleType) -> Iterator[Connection]:
    metadata = sa.MetaData()
    _legacy_tables(metadata)
    engine = sa.create_engine("sqlite:///:memory:", hide_parameters=True)
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(sa.text(
                "INSERT INTO personas (id, name, demographics, goals, grounding_score, confidence) "
                "VALUES ('complete', 'Complete persona', '{\"age\": 31}', '[\"ship\"]', 0.7, 0.9), "
                "('sparse', 'Sparse legacy persona', NULL, NULL, NULL, NULL)"
            ))
            connection.execute(sa.text(
                "INSERT INTO conversations (id, study_id, user_id, generation_run_id, status) "
                "VALUES ('legacy-conversation', 'legacy-study', 'legacy-user', 'legacy-run', 'completed')"
            ))
            connection.execute(sa.text(
                "INSERT INTO conversation_turns (id, conversation_id, role) VALUES ('turn-1', 'legacy-conversation', 'interviewer')"
            ))
            connection.execute(sa.text(
                "INSERT INTO email_verification_tokens (id, user_id, token) VALUES ('token-1', 'legacy-user', 'retained-token')"
            ))
            monkeypatch.setattr(reconcile_revision, "op", Operations(MigrationContext.configure(connection)))
            yield connection
    finally:
        engine.dispose()


def _rows(connection: Connection, table: str) -> list[dict]:
    return [dict(row) for row in connection.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()]


def test_reconciliation_is_the_single_head_after_the_report_backstops(reconcile_revision: ModuleType) -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))
    assert scripts.get_heads() == [REVISION]
    assert reconcile_revision.down_revision == PREDECESSOR
    assert scripts.get_revision(PREDECESSOR).down_revision == "e7a9c1d3f205"


def test_legacy_shape_converges_and_rows_are_retained(legacy_connection: Connection, reconcile_revision: ModuleType) -> None:
    conversations_before = _rows(legacy_connection, "conversations")
    tokens_before = _rows(legacy_connection, "email_verification_tokens")

    reconcile_revision.upgrade()
    reconcile_revision.upgrade()

    inspector = sa.inspect(legacy_connection)
    personas = {row["id"]: row for row in _rows(legacy_connection, "personas")}
    assert personas["complete"]["demographics"] == '{"age": 31}'
    assert personas["complete"]["grounding_score"] == 0.7
    assert personas["sparse"]["demographics"] == "{}"
    assert personas["sparse"]["goals"] == "[]"
    assert personas["sparse"]["grounding_score"] == 0.0
    assert personas["sparse"]["confidence"] == 0.0
    nullable = {column["name"]: column["nullable"] for column in inspector.get_columns("personas")}
    assert not any(nullable[name] for name in (*PERSONA_JSON, *PERSONA_FLOATS))

    assert _rows(legacy_connection, "conversations") == conversations_before
    conversation_indexes = {index["name"] for index in inspector.get_indexes("conversations")}
    assert {"ix_conversations_study_id", "ix_conversations_user_id", "ix_conversations_generation_run_id"} <= conversation_indexes
    assert {column["name"]: column["type"].length for column in inspector.get_columns("conversations")}["status"] == 32
    assert {column["name"]: column["type"].length for column in inspector.get_columns("conversation_turns")}["role"] == 32

    assert _rows(legacy_connection, "email_verification_tokens") == tokens_before
    assert inspector.get_unique_constraints("email_verification_tokens") == []
    token_index = next(index for index in inspector.get_indexes("email_verification_tokens") if index["name"] == "ix_email_verification_tokens_token")
    assert token_index["unique"]
    with pytest.raises(sa.exc.IntegrityError):
        legacy_connection.execute(sa.text(
            "INSERT INTO email_verification_tokens (id, user_id, token) VALUES ('token-2', 'other-user', 'retained-token')"
        ))


def test_offline_postgresql_sql_tolerates_both_shapes_and_deletes_nothing(reconcile_revision: ModuleType) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, f"{PREDECESSOR}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "CREATE INDEX IF NOT EXISTS ix_conversations_study_id ON conversations (study_id)" in sql
    assert "DROP CONSTRAINT IF EXISTS email_verification_tokens_token_key" in sql
    assert "CREATE UNIQUE INDEX ix_email_verification_tokens_token ON email_verification_tokens (token)" in sql
    assert sql.count("SET NOT NULL") == len(PERSONA_JSON) + len(PERSONA_FLOATS)
    assert "UPDATE personas SET demographics = '{}'::jsonb WHERE demographics IS NULL" in sql
    assert "ALTER TABLE conversation_turns ALTER COLUMN role TYPE VARCHAR(32)" in sql
    assert "DELETE " not in sql and "DROP TABLE" not in sql and "DROP COLUMN" not in sql
