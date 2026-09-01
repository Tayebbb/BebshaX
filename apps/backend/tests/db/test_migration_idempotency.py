"""Guards that revision d8e9f0a1b2c3 is safe on already-bootstrapped databases.

``init_database()`` creates the full ORM schema with ``create_all`` and stamps
empty databases at 9731ddaa8413, so ``saved_audiences`` can already exist on a
database that is one revision behind head. Unguarded DDL raised DuplicateTable
there and deadlocked the startup drift guard.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "d8e9f0a1b2c3_add_saved_audiences_restore_hnsw_fix_confidence.py"
)


class _RecordingOp:
    """Records the DDL a migration would emit instead of executing it."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def f(self, name):
        return name

    def create_table(self, name, *args, **kwargs):
        self.calls.append(("create_table", name))

    def create_index(self, name, table_name, *args, **kwargs):
        self.calls.append(("create_index", name))

    def drop_index(self, name, **kwargs):
        self.calls.append(("drop_index", name))

    def drop_table(self, name):
        self.calls.append(("drop_table", name))

    def alter_column(self, table_name, column_name, **kwargs):
        self.calls.append(("alter_column", f"{table_name}.{column_name}"))

    def execute(self, statement):
        self.calls.append(("execute", str(statement)))

    def names(self, kind: str) -> list[str]:
        return [name for called_kind, name in self.calls if called_kind == kind]


class _FakeInspector:
    def __init__(self, tables: set[str], indexes: dict[str, list[str]]):
        self._tables = tables
        self._indexes = indexes

    def get_table_names(self):
        return sorted(self._tables)

    def get_indexes(self, table_name):
        return [{"name": name} for name in self._indexes.get(table_name, [])]


def _run(direction: str, tables: set[str], indexes: dict[str, list[str]]) -> _RecordingOp:
    spec = importlib.util.spec_from_file_location("migration_d8e9f0a1b2c3", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    recorder = _RecordingOp()
    inspector = _FakeInspector(tables, indexes)
    with patch.object(module, "op", recorder), patch("sqlalchemy.inspect", return_value=inspector):
        getattr(module, direction)()
    return recorder


_AUDIENCE_INDEXES = ["ix_saved_audiences_user_id", "ix_saved_audiences_study_id"]


def test_upgrade_creates_table_on_fresh_database():
    recorder = _run("upgrade", tables=set(), indexes={})

    assert recorder.names("create_table") == ["saved_audiences"]
    assert sorted(recorder.names("create_index")) == sorted(_AUDIENCE_INDEXES)


def test_upgrade_skips_existing_table_on_bootstrapped_database():
    """create_all already made the table; re-creating it raises DuplicateTable."""
    recorder = _run(
        "upgrade",
        tables={"saved_audiences"},
        indexes={"saved_audiences": _AUDIENCE_INDEXES},
    )

    assert recorder.names("create_table") == []
    assert recorder.names("create_index") == []


def test_upgrade_backfills_missing_indexes_on_existing_table():
    recorder = _run("upgrade", tables={"saved_audiences"}, indexes={"saved_audiences": []})

    assert recorder.names("create_table") == []
    assert sorted(recorder.names("create_index")) == sorted(_AUDIENCE_INDEXES)


def test_upgrade_always_reasserts_hnsw_and_confidence_defaults():
    for tables, indexes in (
        (set(), {}),
        ({"saved_audiences"}, {"saved_audiences": _AUDIENCE_INDEXES}),
    ):
        recorder = _run("upgrade", tables=tables, indexes=indexes)

        hnsw = [sql for sql in recorder.names("execute") if "ix_memory_items_embedding_hnsw" in sql]
        assert len(hnsw) == 1
        assert "CREATE INDEX IF NOT EXISTS" in hnsw[0]
        assert len(recorder.names("alter_column")) == 4


def test_downgrade_does_not_drop_hnsw_index_owned_by_ancestor():
    """b9d4e5f60a17 owns ix_memory_items_embedding_hnsw; this revision only re-asserts it."""
    recorder = _run(
        "downgrade",
        tables={"saved_audiences"},
        indexes={"saved_audiences": _AUDIENCE_INDEXES},
    )

    assert not [sql for sql in recorder.names("execute") if "DROP INDEX" in sql.upper()]
    assert recorder.names("drop_table") == ["saved_audiences"]
    assert sorted(recorder.names("drop_index")) == sorted(_AUDIENCE_INDEXES)


def test_downgrade_is_safe_when_table_is_absent():
    recorder = _run("downgrade", tables=set(), indexes={})

    assert recorder.names("drop_table") == []
    assert recorder.names("drop_index") == []
    assert len(recorder.names("alter_column")) == 4
