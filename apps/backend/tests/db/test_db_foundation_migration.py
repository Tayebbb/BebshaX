"""Validate the additive HNSW repair using migration scripts and offline operators."""

import importlib.util
from io import StringIO
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from bebshax.db.engine import _alembic_script_head
from bebshax.db.models import Base

REPAIR_REVISION = "b1bf09c4d2e7"
PREDECESSOR = "a9c2e7b6d410"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"


@pytest.fixture
def foundation_repair():
    migration_path = SCRIPT_PATH / "versions" / f"{REPAIR_REVISION}_repair_vector_indexes.py"
    assert migration_path.is_file(), "The additive HNSW repair migration must exist"
    spec = importlib.util.spec_from_file_location("foundation_hnsw_repair", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _offline_sql(monkeypatch, migration, dialect: str, direction: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name=dialect, opts={"as_sql": True, "output_buffer": output}
    )
    monkeypatch.setattr(migration, "op", Operations(context))
    getattr(migration, direction)()
    return output.getvalue()


def test_repair_revision_is_on_the_single_source_head_chain(foundation_repair, monkeypatch, tmp_path) -> None:
    script = ScriptDirectory(str(SCRIPT_PATH))
    heads = script.get_heads()
    assert len(heads) == 1
    assert foundation_repair.revision == REPAIR_REVISION
    assert foundation_repair.down_revision == PREDECESSOR
    assert len(REPAIR_REVISION) <= 32
    assert REPAIR_REVISION in {revision.revision for revision in script.walk_revisions()}
    assert script.get_revision(REPAIR_REVISION).down_revision == PREDECESSOR
    monkeypatch.chdir(tmp_path)
    assert _alembic_script_head() == heads[0]


def test_repair_offline_sql_matches_metadata_without_duplicate_indexes(monkeypatch, foundation_repair) -> None:
    sql = _offline_sql(monkeypatch, foundation_repair, "postgresql", "upgrade")

    assert sql.count("CREATE INDEX IF NOT EXISTS") == 2
    assert "DROP" not in sql
    assert "ALTER" not in sql
    for table_name in ("evidence_chunks", "memory_items"):
        index_name = f"ix_{table_name}_embedding_hnsw"
        index = next(index for index in Base.metadata.tables[table_name].indexes if index.name == index_name)
        expected = str(CreateIndex(index, if_not_exists=True).compile(dialect=postgresql.dialect()))
        assert f"{expected};" in sql
        assert sql.count(index_name) == 1


def test_repair_upgrade_is_a_noop_on_sqlite(monkeypatch, foundation_repair) -> None:
    assert _offline_sql(monkeypatch, foundation_repair, "sqlite", "upgrade") == ""


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_repair_downgrade_preserves_indexes_owned_by_ancestors(monkeypatch, foundation_repair, dialect: str) -> None:
    assert _offline_sql(monkeypatch, foundation_repair, dialect, "downgrade") == ""