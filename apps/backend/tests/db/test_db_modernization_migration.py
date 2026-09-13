"""Frozen migration/schema contracts; PostgreSQL execution is tested separately."""

import ast
import importlib.util
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateColumn, CreateIndex

from bebshax.db.engine import get_metadata


REVISION = "c6f8a2d4e901"
CURRENT_HEAD = "1a3c5e7f9b2d"
PREDECESSOR = "b1bf09c4d2e7"
PREMODERNIZATION = "a9c2e7b6d410"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"
NEW_TABLES = {
    "job_owners", "durable_jobs", "job_attempts", "job_checkpoints",
    "job_file_cleanup", "dataset_versions", "persona_versions", "auth_sessions", "auth_rate_limits",
}
ADDED_COLUMNS = {
    ("users", "role"),
    ("users", "legacy_tokens_revoked_at"),
    ("studies", "revision"),
    ("email_verification_tokens", "purpose"),
    ("email_verification_tokens", "failed_attempts"),
    ("email_verification_tokens", "session_version"),
    ("conversations", "persona_snapshot"),
    ("llm_requests", "owner_id"),
    ("memory_items", "owner_id"),
    ("behavioral_test_runs", "job_id"),
    ("behavioral_test_runs", "execution_token"),
    ("behavioral_test_runs", "input_manifest"),
}


def _table_contract(table, dialect, ignored_constraints: frozenset[str] = frozenset()) -> tuple:
    return (
        tuple(str(CreateColumn(column).compile(dialect=dialect)) for column in table.columns),
        tuple(table.primary_key.columns.keys()),
        {(constraint.name, tuple(constraint.columns.keys())) for constraint in table.constraints
         if isinstance(constraint, sa.UniqueConstraint) and constraint.name not in ignored_constraints},
        {(constraint.name, str(constraint.sqltext)) for constraint in table.constraints
         if isinstance(constraint, sa.CheckConstraint)},
        {(tuple(element.parent.name for element in constraint.elements),
          tuple(element.target_fullname for element in constraint.elements), constraint.ondelete)
         for constraint in table.foreign_key_constraints},
    )


@pytest.fixture
def modernization_revision():
    path = SCRIPT_PATH / "versions" / f"{REVISION}_modernization_schema_parity.py"
    assert path.is_file(), "One additive modernization integration revision must exist"
    spec = importlib.util.spec_from_file_location("modernization_schema_parity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_modernization_is_one_revision_after_existing_head(modernization_revision) -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))

    assert scripts.get_heads() == [CURRENT_HEAD]
    assert scripts.get_revision(CURRENT_HEAD).down_revision == "f2b4d6e8a013"
    assert scripts.get_revision("f2b4d6e8a013").down_revision == "e7a9c1d3f205"
    assert scripts.get_revision("e7a9c1d3f205").down_revision == "d4e6f8a0b219"
    assert scripts.get_revision("d4e6f8a0b219").down_revision == REVISION
    assert modernization_revision.revision == REVISION
    assert modernization_revision.down_revision == PREDECESSOR
    assert [revision.revision for revision in scripts.iterate_revisions(REVISION, PREDECESSOR)] == [REVISION]
    assert scripts.get_revision(PREDECESSOR).down_revision == PREMODERNIZATION


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect()])
def test_frozen_new_tables_and_indexes_match_current_orm(modernization_revision, dialect) -> None:
    metadata = get_metadata()
    tables = modernization_revision._new_tables()

    assert {table.name for table in tables} == NEW_TABLES
    for table in tables:
        expected = metadata.tables[table.name]
        later_constraints = frozenset(
            constraint.name
            for script in ScriptDirectory(str(SCRIPT_PATH)).iterate_revisions("head", REVISION)
            for table_name, constraint in getattr(script.module, "_added_constraints", lambda: ())()
            if table_name == table.name
        )
        assert _table_contract(table, dialect) == _table_contract(expected, dialect, later_constraints), table.name
        assert {str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes} == {
            str(CreateIndex(index).compile(dialect=dialect)) for index in expected.indexes
        }, table.name


def test_frozen_added_columns_match_current_orm(modernization_revision) -> None:
    metadata = get_metadata()
    columns = modernization_revision._added_columns()

    assert {(table_name, column.name) for table_name, column in columns} == ADDED_COLUMNS
    for table_name, column in columns:
        expected = metadata.tables[table_name].c[column.name]
        assert column.nullable == expected.nullable
        assert str(column.type.compile(dialect=postgresql.dialect())) == str(
            expected.type.compile(dialect=postgresql.dialect())
        )
        assert str(column.server_default.arg if column.server_default is not None else None) == str(
            expected.server_default.arg if expected.server_default is not None else None
        )


def test_every_declared_table_and_column_has_migration_coverage(modernization_revision) -> None:
    declared = {}
    scripts = ScriptDirectory(str(SCRIPT_PATH))
    for script in scripts.iterate_revisions(PREDECESSOR, "base"):
        tree = ast.parse(Path(script.path).read_text(encoding="utf-8"))
        upgrade = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade")
        for call in ast.walk(upgrade):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr not in {"create_table", "add_column"} or not call.args:
                continue
            table_node = call.args[0]
            if not isinstance(table_node, ast.Constant) or not isinstance(table_node.value, str):
                continue
            columns = declared.setdefault(table_node.value, set())
            for column in call.args[1:]:
                if (isinstance(column, ast.Call) and isinstance(column.func, ast.Attribute)
                        and column.func.attr == "Column" and column.args
                        and isinstance(column.args[0], ast.Constant)):
                    columns.add(column.args[0].value)
        for block in (node for node in ast.walk(upgrade) if isinstance(node, ast.With)):
            for item in block.items:
                manager = item.context_expr
                if (not isinstance(manager, ast.Call) or not isinstance(manager.func, ast.Attribute)
                        or manager.func.attr != "batch_alter_table" or not manager.args
                        or not isinstance(manager.args[0], ast.Constant)):
                    continue
                columns = declared.setdefault(manager.args[0].value, set())
                for call in ast.walk(block):
                    if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                            and call.func.attr == "add_column" and call.args):
                        column = call.args[0]
                        if (isinstance(column, ast.Call) and isinstance(column.func, ast.Attribute)
                                and column.func.attr == "Column" and column.args
                                and isinstance(column.args[0], ast.Constant)):
                            columns.add(column.args[0].value)
    for script in reversed(list(scripts.iterate_revisions("head", PREDECESSOR))):
        for table in getattr(script.module, "_new_tables", lambda: ())():
            declared[table.name] = set(table.columns.keys())
        for table_name, column in getattr(script.module, "_added_columns", lambda: ())():
            declared[table_name].add(column.name)

    metadata = get_metadata()
    assert set(declared) == set(metadata.tables)
    assert {name: set(table.columns.keys()) - declared[name] for name, table in metadata.tables.items()
            if set(table.columns.keys()) - declared[name]} == {}


@pytest.mark.parametrize("kind", ["indexes", "constraints"])
def test_metadata_named_schema_objects_have_migration_definitions(kind: str) -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))
    identifiers = {
        node.value
        for script in scripts.iterate_revisions("head", "base")
        for node in ast.walk(ast.parse(Path(script.path).read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    missing = {
        (table.name, item.name)
        for table in get_metadata().tables.values()
        for item in getattr(table, kind)
        if item.name is not None and item.name not in identifiers
    }

    assert sorted(missing) == []


def test_postmodernization_offline_sql_is_additive_and_complete(modernization_revision) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"
    output = StringIO()
    config.output_buffer = output

    command.upgrade(config, f"{PREMODERNIZATION}:{REVISION}", sql=True)

    sql = output.getvalue()
    for table_name in NEW_TABLES:
        assert f"CREATE TABLE {table_name} (" in sql
    for table_name, column_name in ADDED_COLUMNS:
        assert f"ALTER TABLE {table_name} ADD COLUMN {column_name} " in sql
    assert "uq_memory_owner_persona_content" in sql
    assert "uq_behavioral_run_persona" in sql
    assert "ck_users_role" in sql
    assert "ix_llm_requests_owner_created_at" in sql
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert sql.count("USING hnsw") == 2
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE llm_requests" not in sql
    assert "COMMIT;" in sql


def test_modernization_downgrade_refuses_implicit_data_loss(monkeypatch, modernization_revision) -> None:
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True})
    monkeypatch.setattr(modernization_revision, "op", Operations(context))

    with pytest.raises(RuntimeError, match="downgrade"):
        modernization_revision.downgrade()


@pytest.fixture
def legacy_slice(monkeypatch, modernization_revision):
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(64), primary_key=True))
    personas = sa.Table(
        "personas", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("study_id", sa.String(64), nullable=True),
        sa.Column("business_id", sa.String(64), nullable=True),
        sa.Column("personality", sa.JSON(), nullable=True),
        sa.Column("detailed_attributes", sa.JSON(), nullable=True),
    )
    sa.Table("dataset_sources", metadata, sa.Column("id", sa.String(64), primary_key=True))
    businesses = sa.Table(
        "businesses", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=True),
    )
    studies = sa.Table(
        "studies", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
    )
    tokens = sa.Table("email_verification_tokens", metadata, sa.Column("id", sa.String(36), primary_key=True))
    sa.Table(
        "conversations", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("study_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    requests = sa.Table(
        "llm_requests", metadata,
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.JSON(), nullable=False),
    )
    memory = sa.Table(
        "memory_items", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("persona_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
    )
    sa.Table("behavioral_test_runs", metadata, sa.Column("id", sa.String(64), primary_key=True))
    results = sa.Table(
        "behavioral_test_results", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("test_run_id", sa.String(64), nullable=False),
        sa.Column("persona_id", sa.String(64), nullable=False),
    )
    engine = sa.create_engine("sqlite:///:memory:", hide_parameters=True)
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(sa.text("INSERT INTO users (id) VALUES ('synthetic-owner')"))
            connection.execute(
                businesses.insert().values(id="legacy-business", owner_id="synthetic-owner")
            )
            connection.execute(personas.insert(), [
                {"id": "legacy-persona", "owner_id": "synthetic-owner", "personality": sa.JSON.NULL,
                 "business_id": "legacy-business",
                 "detailed_attributes": {"preserved": ["complete", "profile"]}},
            ])
            connection.execute(sa.text("UPDATE personas SET personality = NULL"))
            connection.execute(studies.insert().values(id="legacy-study", user_id="synthetic-owner"))
            connection.execute(tokens.insert().values(id="legacy-token"))
            connection.execute(sa.text(
                "INSERT INTO conversations (id, persona_id, user_id, study_id, created_at, started_at) "
                "VALUES ('legacy-conversation', 'legacy-persona', 'synthetic-owner', 'legacy-study', '2026-09-09 00:00:00', NULL)"
            ))
            connection.execute(requests.insert().values(request_id="legacy-request", attempts=[{"complete": "trace"}]))
            connection.execute(memory.insert().values(
                id="legacy-memory", persona_id="legacy-persona", conversation_id="legacy-conversation",
                content_hash="synthetic-hash", text="Unabridged synthetic memory",
            ))
            connection.execute(results.insert().values(id="legacy-result", test_run_id="legacy-run", persona_id="legacy-persona"))
            context = MigrationContext.configure(connection)
            monkeypatch.setattr(modernization_revision, "op", Operations(context))
            yield connection
    finally:
        engine.dispose()


def test_migration_preserves_legacy_slice_and_is_repeatable(legacy_slice, modernization_revision) -> None:
    modernization_revision.upgrade()
    modernization_revision.upgrade()

    assert NEW_TABLES <= set(sa.inspect(legacy_slice).get_table_names())
    assert legacy_slice.execute(sa.text("SELECT revision FROM studies")).scalar_one() == 1
    assert legacy_slice.execute(sa.text("SELECT purpose, failed_attempts FROM email_verification_tokens")).one() == (
        "email-verification", 0,
    )
    memory = legacy_slice.execute(sa.text("SELECT owner_id, text, content_hash FROM memory_items")).one()
    assert memory == ("synthetic-owner", "Unabridged synthetic memory", "synthetic-hash")
    request = legacy_slice.execute(sa.text("SELECT owner_id, attempts FROM llm_requests")).one()
    assert request.owner_id is None
    assert "complete" in request.attempts and "trace" in request.attempts
    persona = legacy_slice.execute(sa.text("SELECT personality, detailed_attributes FROM personas")).one()
    assert persona.personality == "{}"
    assert "complete" in persona.detailed_attributes and "profile" in persona.detailed_attributes
    columns = {column["name"]: column for column in sa.inspect(legacy_slice).get_columns("personas")}
    assert columns["personality"]["nullable"] is False
    assert columns["detailed_attributes"]["nullable"] is False
    conversation = legacy_slice.execute(sa.text("SELECT created_at, started_at, persona_snapshot FROM conversations")).one()
    assert conversation.created_at == conversation.started_at
    assert conversation.persona_snapshot is None
    assert legacy_slice.execute(sa.text("SELECT session_version FROM email_verification_tokens")).scalar_one() == 0
    assert legacy_slice.execute(sa.text("SELECT role FROM users WHERE id = 'synthetic-owner'")).scalar_one() == "user"


def test_memory_backfill_uses_each_private_conversation_on_a_shared_persona(legacy_slice, modernization_revision) -> None:
    legacy_slice.execute(sa.text("INSERT INTO users (id) VALUES ('synthetic-other'), ('usr_system_holder')"))
    legacy_slice.execute(sa.text("UPDATE personas SET owner_id = 'usr_system_holder', business_id = NULL"))
    legacy_slice.execute(sa.text("INSERT INTO studies (id, user_id) VALUES ('other-study', 'synthetic-other')"))
    legacy_slice.execute(sa.text(
        "INSERT INTO conversations (id, persona_id, user_id, study_id, created_at) "
        "VALUES ('other-conversation', 'legacy-persona', 'synthetic-other', 'other-study', '2026-09-09 00:00:00')"
    ))
    legacy_slice.execute(sa.text(
        "INSERT INTO memory_items (id, persona_id, conversation_id, content_hash, text) "
        "VALUES ('other-memory', 'legacy-persona', 'other-conversation', 'synthetic-hash', 'Other private memory')"
    ))

    modernization_revision.upgrade()
    modernization_revision.upgrade()

    assert dict(legacy_slice.execute(sa.text("SELECT id, owner_id FROM memory_items")).tuples().all()) == {
        "legacy-memory": "synthetic-owner", "other-memory": "synthetic-other",
    }


@pytest.mark.parametrize("break_link", [
    "UPDATE memory_items SET conversation_id = NULL",
    "UPDATE memory_items SET conversation_id = 'missing-conversation'",
    "UPDATE conversations SET user_id = NULL",
    "UPDATE conversations SET user_id = 'usr_system_holder'",
    "UPDATE conversations SET user_id = 'missing-user'",
    "UPDATE conversations SET persona_id = 'different-persona'",
    "UPDATE conversations SET study_id = 'missing-study'",
    "UPDATE studies SET user_id = NULL",
    "UPDATE studies SET user_id = 'synthetic-other'",
    "UPDATE personas SET owner_id = 'synthetic-other'",
    "UPDATE personas SET user_id = 'synthetic-other'",
    "UPDATE personas SET business_id = 'missing-business'",
    "UPDATE businesses SET owner_id = 'synthetic-other'",
    "UPDATE personas SET study_id = 'different-study'",
])
def test_memory_backfill_quarantines_ambiguous_or_reparented_links(
    legacy_slice, modernization_revision, break_link: str,
) -> None:
    legacy_slice.execute(sa.text("INSERT INTO users (id) VALUES ('synthetic-other'), ('usr_system_holder')"))
    legacy_slice.execute(sa.text(break_link))

    modernization_revision.upgrade()

    assert legacy_slice.execute(sa.text("SELECT owner_id FROM memory_items")).scalar_one() is None
    assert legacy_slice.execute(sa.text("SELECT text FROM memory_items")).scalar_one() == "Unabridged synthetic memory"


def test_memory_backfill_preserves_preexisting_attribution(legacy_slice, modernization_revision) -> None:
    legacy_slice.execute(sa.text("ALTER TABLE memory_items ADD COLUMN owner_id VARCHAR(64)"))
    legacy_slice.execute(sa.text("UPDATE memory_items SET owner_id = 'recorded-at-write-time'"))
    legacy_slice.execute(sa.text("UPDATE personas SET owner_id = 'reparented-owner'"))

    modernization_revision.upgrade()

    assert legacy_slice.execute(sa.text("SELECT owner_id FROM memory_items")).scalar_one() == "recorded-at-write-time"


def test_precreated_tables_preserve_rows_and_repair_missing_index(legacy_slice, modernization_revision) -> None:
    for table in modernization_revision._new_tables():
        table.create(legacy_slice)
    legacy_slice.execute(sa.text("INSERT INTO job_owners (owner_id, revision) VALUES ('preserved-owner', 7)"))
    legacy_slice.execute(sa.text("DROP INDEX ix_jobs_recovery"))

    modernization_revision.upgrade()

    assert legacy_slice.execute(sa.text("SELECT revision FROM job_owners WHERE owner_id = 'preserved-owner'")).scalar_one() == 7
    assert "ix_jobs_recovery" in {index["name"] for index in sa.inspect(legacy_slice).get_indexes("durable_jobs")}


def test_conflicting_precreated_table_is_not_silently_accepted(legacy_slice, modernization_revision) -> None:
    legacy_slice.execute(sa.text("CREATE TABLE job_owners (owner_id VARCHAR(255) PRIMARY KEY, revision TEXT)"))

    with pytest.raises(RuntimeError, match="conflict"):
        modernization_revision.upgrade()

    assert "durable_jobs" not in sa.inspect(legacy_slice).get_table_names()
    assert legacy_slice.execute(sa.text("SELECT text FROM memory_items")).scalar_one() == "Unabridged synthetic memory"


@pytest.mark.parametrize("table_name", ["memory_items", "behavioral_test_results"])
def test_legacy_duplicates_block_upgrade_without_deleting_rows(legacy_slice, modernization_revision, table_name: str) -> None:
    if table_name == "memory_items":
        legacy_slice.execute(sa.text(
            "INSERT INTO memory_items (id, persona_id, conversation_id, content_hash, text) "
            "VALUES ('duplicate-memory', 'legacy-persona', 'legacy-conversation', 'synthetic-hash', 'Second full memory')"
        ))
    else:
        legacy_slice.execute(sa.text(
            "INSERT INTO behavioral_test_results (id, test_run_id, persona_id) "
            "VALUES ('duplicate-result', 'legacy-run', 'legacy-persona')"
        ))

    with pytest.raises(RuntimeError, match="Legacy duplicates"):
        modernization_revision.upgrade()

    table = sa.table(table_name)
    assert legacy_slice.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 2


def test_migration_preserves_preexisting_memory_owner(legacy_slice, modernization_revision) -> None:
    legacy_slice.execute(sa.text("ALTER TABLE memory_items ADD COLUMN owner_id VARCHAR(64)"))
    legacy_slice.execute(sa.text("UPDATE memory_items SET owner_id = 'original-owner'"))

    modernization_revision.upgrade()

    assert legacy_slice.execute(sa.text("SELECT owner_id FROM memory_items")).scalar_one() == "original-owner"


def test_user_role_check_rejects_unknown_privilege(legacy_slice, modernization_revision) -> None:
    modernization_revision.upgrade()

    with pytest.raises(IntegrityError):
        legacy_slice.execute(sa.text("INSERT INTO users (id, role) VALUES ('unknown-role', 'superadmin')"))