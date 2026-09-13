"""Frozen, additive M4/M5 DDL and synthetic legacy upgrades."""

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
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable

from bebshax.db.engine import get_metadata


REVISION = "e7a9c1d3f205"
PREDECESSOR = "d4e6f8a0b219"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"


@pytest.fixture
def source_revision():
    path = SCRIPT_PATH / "versions" / f"{REVISION}_persona_source_ledger.py"
    assert path.is_file(), "Typed dataset lineage and source reservations require a forward migration"
    return ScriptDirectory(str(SCRIPT_PATH)).get_revision(REVISION).module


def test_source_ledger_is_one_forward_revision(source_revision) -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))
    assert scripts.get_heads() == ["1a3c5e7f9b2d"]
    assert scripts.get_revision("1a3c5e7f9b2d").down_revision == "f2b4d6e8a013"
    assert scripts.get_revision("f2b4d6e8a013").down_revision == REVISION
    assert source_revision.down_revision == PREDECESSOR
    assert [script.revision for script in scripts.iterate_revisions(REVISION, PREDECESSOR)] == [REVISION]


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect()])
def test_source_ledger_frozen_ddl_matches_orm(source_revision, dialect) -> None:
    metadata = get_metadata()
    [table] = source_revision._new_tables()
    expected = metadata.tables["persona_source_selections"]
    assert str(CreateTable(table).compile(dialect=dialect)) == str(CreateTable(expected).compile(dialect=dialect))
    assert {str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes} == {
        str(CreateIndex(index).compile(dialect=dialect)) for index in expected.indexes
    }
    for table_name, column in source_revision._added_columns():
        assert str(CreateColumn(column).compile(dialect=dialect)) == str(
            CreateColumn(metadata.tables[table_name].c[column.name]).compile(dialect=dialect)
        )
    for table_name, constraint in source_revision._added_constraints():
        expected_constraint = next(item for item in metadata.tables[table_name].constraints if item.name == constraint.name)
        assert tuple(constraint.columns.keys()) == tuple(expected_constraint.columns.keys())
        if isinstance(constraint, sa.CheckConstraint):
            assert str(constraint.sqltext) == str(expected_constraint.sqltext)
        if isinstance(constraint, sa.ForeignKeyConstraint):
            assert [item.target_fullname for item in constraint.elements] == [
                item.target_fullname for item in expected_constraint.elements
            ]


@pytest.fixture
def preledger_connection(monkeypatch, source_revision):
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(64), primary_key=True))
    for name, owner_name in (
        ("studies", "user_id"), ("businesses", "owner_id"),
        ("dataset_sources", "user_id"), ("dataset_persona_runs", "user_id"),
    ):
        sa.Table(name, metadata, sa.Column("id", sa.String(64), primary_key=True), sa.Column(owner_name, sa.String(64)))
    sa.Table("dataset_versions", metadata, sa.Column("id", sa.String(64), primary_key=True))
    sa.Table(
        "personas", metadata,
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("generation_run_id", sa.String(64)), sa.Column("segment_id", sa.String(64)),
        sa.Column("detailed_attributes", sa.JSON(), nullable=False),
    )
    old_revision = ScriptDirectory(str(SCRIPT_PATH)).get_revision("c6f8a2d4e901").module
    next(table for table in old_revision._new_tables() if table.name == "persona_versions").to_metadata(metadata)
    engine = sa.create_engine("sqlite:///:memory:", hide_parameters=True)
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(sa.text("INSERT INTO users (id) VALUES ('synthetic-owner')"))
            connection.execute(sa.text(
                "INSERT INTO personas (id, owner_id, generation_run_id, segment_id, detailed_attributes) "
                "VALUES ('legacy-persona', 'synthetic-owner', 'ambiguous-run', 'ambiguous-segment', '{\"complete\": true}')"
            ))
            connection.execute(sa.text(
                "INSERT INTO persona_versions (persona_id, version, owner_id, snapshot, capture_kind, captured_at) "
                "VALUES ('legacy-persona', 7, 'synthetic-owner', '{\"complete\": true}', 'observed_current', '2026-09-09 00:00:00')"
            ))
            monkeypatch.setattr(source_revision, "op", Operations(MigrationContext.configure(connection)))
            yield connection
    finally:
        engine.dispose()


def test_source_migration_retains_legacy_aliases_without_guessing_ids(preledger_connection, source_revision) -> None:
    source_revision.upgrade()
    source_revision.upgrade()
    row = preledger_connection.execute(sa.text("SELECT * FROM personas")).mappings().one()
    assert row["generation_run_id"] == "ambiguous-run"
    assert row["segment_id"] == "ambiguous-segment"
    assert row["dataset_persona_run_id"] is row["dataset_version_id"] is row["dataset_segment_key"] is None
    assert row["detailed_attributes"] == '{"complete": true}'
    assert preledger_connection.scalar(sa.text("SELECT version FROM persona_versions")) == 7
    assert preledger_connection.scalar(sa.text("SELECT count(*) FROM persona_source_selections")) == 0


def test_conflicting_typed_column_blocks_before_other_schema_changes(preledger_connection, source_revision) -> None:
    preledger_connection.execute(sa.text("ALTER TABLE personas ADD COLUMN dataset_version_id INTEGER"))
    with pytest.raises(RuntimeError, match="conflict"):
        source_revision.upgrade()
    assert "dataset_persona_run_id" not in {column["name"] for column in sa.inspect(preledger_connection).get_columns("personas")}
    assert "persona_source_selections" not in sa.inspect(preledger_connection).get_table_names()


def test_conflicting_existing_source_table_is_not_silently_accepted(preledger_connection, source_revision) -> None:
    preledger_connection.execute(sa.text("CREATE TABLE persona_source_selections (id INTEGER PRIMARY KEY)"))
    with pytest.raises(RuntimeError, match="conflict"):
        source_revision.upgrade()


def test_same_named_weakened_check_is_rejected(preledger_connection, source_revision) -> None:
    for table_name, constraint in source_revision._added_constraints():
        if isinstance(constraint, sa.UniqueConstraint):
            with source_revision.op.batch_alter_table(table_name) as batch:
                batch.create_unique_constraint(constraint.name, list(constraint.columns.keys()))
    [table] = source_revision._new_tables()
    next(constraint for constraint in table.constraints if constraint.name == "ck_source_selection_one_scope").sqltext = sa.text("TRUE")
    table.create(preledger_connection)

    with pytest.raises(RuntimeError, match="conflict"):
        source_revision.upgrade()


@pytest.mark.parametrize("predicate, accepted", [
    ("((released_at IS NULL) AND (study_id IS NOT NULL))", True),
    ("((released_at IS NULL) OR (study_id IS NOT NULL))", False),
    (None, False),
])
def test_postgresql_reflected_partial_predicate_is_checked_semantically(source_revision, monkeypatch, predicate, accepted) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock

    [table] = source_revision._new_tables()
    index = next(index for index in table.indexes if index.name == "uq_source_active_study")
    reflected = {
        "name": index.name, "column_names": list(index.columns.keys()), "unique": True,
        "dialect_options": {"postgresql_where": sa.text(predicate)} if predicate else {},
    }
    inspector = SimpleNamespace(get_indexes=lambda _name: [reflected])
    monkeypatch.setattr(source_revision.sa, "inspect", lambda _connection: inspector)
    monkeypatch.setattr(source_revision, "op", SimpleNamespace(
        get_context=lambda: SimpleNamespace(as_sql=False),
        get_bind=lambda: SimpleNamespace(dialect=postgresql.dialect()), invoke=Mock(),
    ))
    if accepted:
        source_revision._ensure_index(index)
        source_revision.op.invoke.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match="conflict"):
            source_revision._ensure_index(index)


def test_source_ledger_offline_sql_preserves_history_and_has_partial_scopes(source_revision) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, f"{PREDECESSOR}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE persona_source_selections" in sql
    for scope in ("study", "business", "dataset"):
        assert f"CREATE UNIQUE INDEX uq_source_active_{scope}" in sql
        assert f"WHERE released_at IS NULL AND {scope}_id IS NOT NULL" in sql
    assert "NOT VALID" in sql and "VALIDATE CONSTRAINT" in sql
    assert "FOREIGN KEY(persona_id, persona_version, persona_owner_id)" in sql
    assert "DROP TABLE" not in sql and "DELETE FROM" not in sql
    assert "UPDATE personas" not in sql and "UPDATE persona_versions" not in sql
    assert "COMMIT;" in sql


def test_source_ledger_downgrade_refuses_history_loss(source_revision) -> None:
    with pytest.raises(RuntimeError, match="downgrade"):
        source_revision.downgrade()