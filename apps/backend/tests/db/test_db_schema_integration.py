"""Schema integration contracts independent of application import side effects."""

import ast
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from bebshax import config as settings_module


BACKEND_PATH = Path(__file__).resolve().parents[2]
PACKAGE_PATH = BACKEND_PATH / "bebshax"
PREMODERNIZATION_REVISION = "a9c2e7b6d410"
VECTOR_REPAIR_REVISION = "b1bf09c4d2e7"


def _migration_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_PATH / "alembic"))
    return config


def _declared_table_names() -> set[str]:
    tables = set()
    for source in PACKAGE_PATH.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            if any(isinstance(target, ast.Name) and target.id == "__tablename__" for target in node.targets):
                tables.add(node.value.value)
    return tables


def test_metadata_registration_covers_all_declared_tables_without_app_import() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; "
            "from bebshax.db.engine import get_metadata; "
            "metadata = get_metadata(); "
            "assert get_metadata() is metadata; "
            "assert 'bebshax.main' not in sys.modules; "
            "print(json.dumps(sorted(metadata.tables)))",
        ],
        cwd=BACKEND_PATH,
        env={
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONPATH": str(BACKEND_PATH),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    registered = set(json.loads(result.stdout))
    assert registered == _declared_table_names()
    assert {
        "job_owners", "durable_jobs", "job_attempts", "job_checkpoints",
        "job_file_cleanup", "dataset_versions", "persona_versions", "auth_sessions", "auth_rate_limits",
    } <= registered
    assert len(registered) > 32


def test_offline_migrations_use_explicit_url_without_configured_settings(monkeypatch) -> None:
    def forbid_settings():
        raise AssertionError("Migration must not read configured settings")

    monkeypatch.setattr(settings_module, "get_settings", forbid_settings)
    config = _migration_config()
    output = StringIO()
    config.output_buffer = output
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"

    command.upgrade(config, f"{PREMODERNIZATION_REVISION}:{VECTOR_REPAIR_REVISION}", sql=True)

    sql = output.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert sql.count("USING hnsw") == 2
    assert "COMMIT;" in sql


def test_migrations_use_supplied_connection_without_configured_settings(monkeypatch) -> None:
    def forbid_settings():
        raise AssertionError("Migration must not read configured settings")

    monkeypatch.setattr(settings_module, "get_settings", forbid_settings)
    config = _migration_config()
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.stamp(config, PREMODERNIZATION_REVISION)
            command.upgrade(config, VECTOR_REPAIR_REVISION)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == VECTOR_REPAIR_REVISION
    finally:
        engine.dispose()