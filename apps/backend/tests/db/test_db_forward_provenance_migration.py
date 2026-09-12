"""Forward-only provenance context migration, independent of live databases."""

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
from sqlalchemy.schema import CreateColumn

from bebshax.db.models import LLMRequests


REVISION = "d4e6f8a0b219"
PREDECESSOR = "c6f8a2d4e901"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"
CONTEXT_COLUMNS = {
    "study_id", "data_classification", "processing_policy_id",
    "processing_provider_allowlist", "processing_openrouter_upstreams", "estimated_tokens",
}


@pytest.fixture
def provenance_revision():
    path = SCRIPT_PATH / "versions" / f"{REVISION}_durable_provenance_context.py"
    assert path.is_file(), "Durable provenance context requires a forward migration"
    specification = importlib.util.spec_from_file_location("durable_provenance_context", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_provenance_context_has_one_forward_head_without_rewriting_parents() -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))

    assert scripts.get_heads() == ["f2b4d6e8a013"]
    assert scripts.get_revision("f2b4d6e8a013").down_revision == "e7a9c1d3f205"
    assert scripts.get_revision("e7a9c1d3f205").down_revision == REVISION
    assert [item.revision for item in scripts.iterate_revisions(REVISION, "a9c2e7b6d410")] == [
        REVISION, PREDECESSOR, "b1bf09c4d2e7",
    ]


@pytest.mark.parametrize("dialect", [postgresql.dialect(), sqlite.dialect()])
def test_provenance_context_column_contract_matches_orm(provenance_revision, dialect) -> None:
    columns = provenance_revision._added_columns()

    assert {(table_name, column.name) for table_name, column in columns} == {
        ("llm_requests", name) for name in CONTEXT_COLUMNS
    }
    for table_name, column in columns:
        assert table_name == "llm_requests"
        expected = LLMRequests.__table__.c[column.name]
        assert str(CreateColumn(column).compile(dialect=dialect)) == str(
            CreateColumn(expected).compile(dialect=dialect)
        )


@pytest.fixture
def legacy_provenance_connection(monkeypatch, provenance_revision):
    table = sa.Table(
        "llm_requests", sa.MetaData(),
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=True),
        sa.Column("attempts", sa.JSON(), nullable=False),
    )
    engine = sa.create_engine("sqlite:///:memory:", hide_parameters=True)
    try:
        with engine.begin() as connection:
            table.create(connection)
            connection.execute(table.insert().values(
                request_id="legacy-request", owner_id=None,
                attempts=[{"provider": "historical-provider", "notes": ["complete historical trace"]}],
            ))
            monkeypatch.setattr(provenance_revision, "op", Operations(MigrationContext.configure(connection)))
            yield connection
    finally:
        engine.dispose()


def test_forward_context_defaults_do_not_invent_historical_policy(
    legacy_provenance_connection, provenance_revision,
) -> None:
    provenance_revision.upgrade()
    provenance_revision.upgrade()

    row = legacy_provenance_connection.execute(sa.text("SELECT * FROM llm_requests")).mappings().one()
    assert row["owner_id"] is None
    assert row["study_id"] is None
    assert row["data_classification"] == "unknown"
    assert row["processing_policy_id"] is None
    assert row["processing_provider_allowlist"] == "[]"
    assert row["processing_openrouter_upstreams"] == "[]"
    assert row["estimated_tokens"] is None
    assert "complete historical trace" in row["attempts"]
    assert "ck_llm_requests_data_classification" in {
        item["name"] for item in sa.inspect(legacy_provenance_connection).get_check_constraints("llm_requests")
    }
    with pytest.raises(IntegrityError):
        legacy_provenance_connection.execute(sa.text(
            "UPDATE llm_requests SET data_classification = 'unapproved'"
        ))


def test_conflicting_precreated_context_aborts_before_schema_changes(
    legacy_provenance_connection, provenance_revision,
) -> None:
    legacy_provenance_connection.execute(sa.text("ALTER TABLE llm_requests ADD COLUMN estimated_tokens TEXT"))

    with pytest.raises(RuntimeError, match="conflict"):
        provenance_revision.upgrade()

    assert "study_id" not in {
        column["name"] for column in sa.inspect(legacy_provenance_connection).get_columns("llm_requests")
    }
    assert legacy_provenance_connection.scalar(sa.text("SELECT COUNT(*) FROM llm_requests")) == 1


def test_forward_context_offline_postgresql_sql_is_additive(provenance_revision) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"
    output = StringIO()
    config.output_buffer = output

    command.upgrade(config, f"{PREDECESSOR}:{REVISION}", sql=True)

    sql = output.getvalue()
    for column_name in CONTEXT_COLUMNS:
        assert f"ALTER TABLE llm_requests ADD COLUMN {column_name} " in sql
    assert "ck_llm_requests_data_classification" in sql
    assert "NOT VALID" in sql
    assert "VALIDATE CONSTRAINT" in sql
    assert "DROP " not in sql
    assert "DELETE " not in sql
    assert "UPDATE llm_requests" not in sql
    assert "COMMIT;" in sql


def test_forward_context_downgrade_refuses_history_loss(provenance_revision) -> None:
    with pytest.raises(RuntimeError, match="downgrade"):
        provenance_revision.downgrade()