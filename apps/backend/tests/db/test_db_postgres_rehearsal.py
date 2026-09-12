"""Opt-in real PostgreSQL checks using only an owned disposable local container."""

from datetime import datetime, timezone
from pathlib import Path
import os
import re
import shutil
import ssl
import subprocess
import time
from types import SimpleNamespace
import uuid

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from bebshax.db.engine import get_metadata, init_database, normalize_async_database_url
from bebshax.db.models import EvidenceChunks
from bebshax.llm.adapters.embeddings import CANONICAL_DIM, EmbeddingBackend
from bebshax.research.vector_search import VectorSearchEngine


pytestmark = pytest.mark.integration
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"
PREMODERNIZATION = "a9c2e7b6d410"
INTEGRATION_REVISION = "c6f8a2d4e901"
REVISION = "f2b4d6e8a013"
FIXED_TIME = datetime(2026, 9, 9, tzinfo=timezone.utc)


class _RehearsalEmbedding(EmbeddingBackend):
    space = "db-integration-space"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (CANONICAL_DIM - 1) for _ in texts]


@pytest.fixture
def disposable_postgres(request, tmp_path):
    if not request.config.getoption("--db-docker"):
        pytest.skip("Requires --db-docker; configured application databases are never used")
    docker = shutil.which("docker")
    if docker is None:
        pytest.fail("Local Docker CLI unavailable; no database was contacted")
    docker_config = tmp_path / "docker-client"
    docker_config.mkdir()
    host = "npipe:////./pipe/dockerDesktopLinuxEngine" if os.name == "nt" else "unix:///var/run/docker.sock"
    base = [docker, "--config", str(docker_config), "--host", host]

    def run(*arguments: str, check: bool = True):
        result = subprocess.run(
            [*base, *arguments], capture_output=True, text=True, timeout=45, check=False,
        )
        if check and result.returncode != 0:
            pytest.fail(f"Disposable local Docker {arguments[0]} failed; configured databases were not used")
        return result

    run("version", "--format", "{{.Server.Version}}")
    run("image", "inspect", "pgvector/pgvector:pg16", "--format", "{{.Id}}")
    identifier = uuid.uuid4().hex
    database = f"integrator_{identifier}"
    container = run(
        "create", "--pull=never", "--name", f"bebshax-db-integrator-{identifier}",
        "--label", "bebshax.test=db-integrator", "--cpus", "1", "--memory", "768m",
        "--pids-limit", "256", "--publish", "127.0.0.1::5432",
        "--tmpfs", "/var/lib/postgresql/data:rw,size=536870912",
        "--env", "POSTGRES_HOST_AUTH_METHOD=trust", "--env", "POSTGRES_USER=db_integrator",
        "--env", f"POSTGRES_DB={database}", "pgvector/pgvector:pg16",
    ).stdout.strip()
    assert re.fullmatch(r"[a-f0-9]{64}", container), "Docker did not return a unique container ID"
    try:
        run("start", container)
        endpoint = run("port", container, "5432/tcp").stdout.strip()
        assert re.fullmatch(r"127\.0\.0\.1:\d+", endpoint), "Test PostgreSQL must be loopback-only"
        port = int(endpoint.rsplit(":", 1)[1])
        deadline = time.monotonic() + 45
        while True:
            ready = run("exec", container, "pg_isready", "-U", "db_integrator", "-d", database, check=False)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                pytest.fail("Disposable PostgreSQL did not become ready within 45 seconds")
            time.sleep(0.2)
        print(f"Disposable PostgreSQL endpoint: 127.0.0.1:{port}")
        yield SimpleNamespace(
            url=f"postgresql+asyncpg://db_integrator@127.0.0.1:{port}/{database}?ssl=disable",
            port=port, database=database, container=container, run=run,
        )
    finally:
        cleanup = run("rm", "--force", container, check=False)
        assert cleanup.returncode == 0, "Owned disposable container cleanup failed"


@pytest_asyncio.fixture
async def rehearsal_engine(disposable_postgres):
    engine = create_async_engine(
        disposable_postgres.url, poolclass=sa.pool.NullPool, hide_parameters=True,
        connect_args={"password": "synthetic-test-only"},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def _upgrade(engine, revision: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))

    def upgrade(connection) -> None:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)


def _assert_parity(connection) -> None:
    metadata = get_metadata()
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    assert context.get_current_heads() == (REVISION,)
    assert set(sa.inspect(connection).get_table_names()) - {"alembic_version"} == set(metadata.tables)
    assert compare_metadata(context, metadata) == []
    for table_name in ("evidence_chunks", "memory_items"):
        definition = connection.execute(sa.text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND indexname = :name"
        ), {"name": f"ix_{table_name}_embedding_hnsw"}).scalar_one()
        assert "USING hnsw (embedding vector_cosine_ops)" in definition
        vector_type = connection.execute(sa.text(
            "SELECT format_type(attribute.atttypid, attribute.atttypmod) FROM pg_attribute attribute "
            "JOIN pg_class relation ON relation.oid = attribute.attrelid "
            "JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = current_schema() AND relation.relname = :name "
            "AND attribute.attname = 'embedding' AND NOT attribute.attisdropped"
        ), {"name": table_name}).scalar_one()
        assert vector_type == f"vector({CANONICAL_DIM})"


def _legacy_values(table, **overrides) -> dict:
    values = {}
    for column in table.columns:
        if column.name in overrides:
            values[column.name] = overrides[column.name]
        elif column.nullable or column.server_default is not None:
            continue
        elif isinstance(column.type, sa.Boolean):
            values[column.name] = False
        elif isinstance(column.type, sa.Integer):
            values[column.name] = 1
        elif isinstance(column.type, sa.Float):
            values[column.name] = 0.25
        elif isinstance(column.type, sa.DateTime):
            values[column.name] = FIXED_TIME
        elif isinstance(column.type, sa.JSON):
            values[column.name] = {}
        elif isinstance(column.type, (sa.String, sa.Text)):
            values[column.name] = "synthetic"
        else:
            raise AssertionError(f"Provide an explicit synthetic value for {table.name}.{column.name}")
    return values


def _plain(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _rows(connection, tables) -> dict:
    allowed_backfills = {("personas", "personality"), ("personas", "detailed_attributes"), ("conversations", "started_at")}
    return {
        table.name: [
            {name: _plain(value) for name, value in row.items() if (table.name, name) not in allowed_backfills}
            for row in connection.execute(sa.select(table).order_by(*table.primary_key.columns)).mappings()
        ]
        for table in tables
    }


def _seed_legacy(connection):
    positive = [1.0] + [0.0] * (CANONICAL_DIM - 1)
    definitions = (
        ("users", {"id": "synthetic-owner", "email": "fixture@example.invalid", "full_name": "Synthetic Owner", "session_version": 7}),
        ("businesses", {"id": "legacy-business", "owner_id": "synthetic-owner", "name": "Synthetic Business"}),
        ("studies", {"id": "legacy-study", "user_id": "synthetic-owner", "title": "Synthetic Study"}),
        ("personas", {"id": "legacy-persona", "owner_id": "synthetic-owner", "business_id": "legacy-business", "study_id": "legacy-study",
                      "name": "Synthetic Persona", "personality": sa.null(), "detailed_attributes": {"identity": "preserved-" * 100}}),
        ("dataset_sources", {"id": "legacy-dataset", "user_id": "synthetic-owner", "study_id": "legacy-study"}),
        ("conversations", {"id": "legacy-conversation", "persona_id": "legacy-persona", "study_id": "legacy-study", "user_id": "synthetic-owner",
                           "objective": "Complete synthetic interview objective", "started_at": sa.null()}),
        ("conversation_turns", {"id": "legacy-turn", "conversation_id": "legacy-conversation", "turn_number": 1,
                                "role": "persona", "content": "Unabridged synthetic transcript " * 100}),
        ("evidence_sources", {"id": "legacy-source", "study_id": "legacy-study", "content_hash": "synthetic-evidence-hash"}),
        ("evidence_chunks", {"id": "legacy-chunk", "source_id": "legacy-source", "study_id": "legacy-study",
                             "embedding": positive, "embedding_space": "db-integration-space", "content": "Unabridged synthetic evidence " * 100}),
        ("memory_items", {"id": "legacy-memory", "persona_id": "legacy-persona", "kind": "episodic", "embedding": positive,
                          "conversation_id": "legacy-conversation", "embedding_space": "db-integration-space",
                          "content_hash": "synthetic-memory-hash", "text": "Unabridged synthetic memory " * 100}),
        ("llm_requests", {"request_id": "legacy-request", "task": "PERSONA_GENERATION", "persona_id": "legacy-persona",
                          "conversation_id": "legacy-conversation", "attempts": [{"complete": "trace-" * 100}], "routing_path": ["historical"]}),
    )
    metadata = sa.MetaData()
    metadata.reflect(connection, only=[name for name, _ in definitions])
    for table_name, values in definitions:
        table = metadata.tables[table_name]
        connection.execute(table.insert().values(**_legacy_values(table, **values)))
    tables = [metadata.tables[name] for name, _ in definitions]
    return tables, _rows(connection, tables)


async def test_fresh_postgresql_full_chain_has_reflected_metadata_parity(rehearsal_engine, monkeypatch) -> None:
    monkeypatch.setattr(sa.MetaData, "create_all", lambda *args, **kwargs: pytest.fail("Fresh PostgreSQL must use Alembic"))

    await _upgrade(rehearsal_engine, REVISION)

    async with rehearsal_engine.connect() as connection:
        await connection.run_sync(_assert_parity)
    assert set(await init_database(rehearsal_engine, seed=False)) == set(get_metadata().tables)


async def test_premodernization_upgrade_preserves_all_seeded_data(rehearsal_engine) -> None:
    await _upgrade(rehearsal_engine, PREMODERNIZATION)
    async with rehearsal_engine.begin() as connection:
        tables, before = await connection.run_sync(_seed_legacy)
        await connection.execute(sa.text("DROP INDEX ix_evidence_chunks_embedding_hnsw"))
        await connection.execute(sa.text("DROP INDEX ix_memory_items_embedding_hnsw"))

    await _upgrade(rehearsal_engine, REVISION)
    await _upgrade(rehearsal_engine, REVISION)

    async with rehearsal_engine.connect() as connection:
        assert await connection.run_sync(lambda sync: _rows(sync, tables)) == before
        await connection.run_sync(_assert_parity)
        assert (await connection.execute(sa.text("SELECT owner_id FROM llm_requests WHERE request_id = 'legacy-request'"))).scalar_one() is None
        assert (await connection.execute(sa.text("SELECT owner_id FROM memory_items WHERE id = 'legacy-memory'"))).scalar_one() == "synthetic-owner"


async def test_existing_new_tables_are_reconciled_without_discarding_rows(rehearsal_engine) -> None:
    await _upgrade(rehearsal_engine, PREMODERNIZATION)
    migration = ScriptDirectory(str(SCRIPT_PATH)).get_revision(INTEGRATION_REVISION).module

    def precreate(connection) -> None:
        for table in migration._new_tables():
            table.create(connection)
        connection.execute(sa.text("INSERT INTO job_owners (owner_id, revision) VALUES ('retained', 4)"))
        connection.execute(sa.text("DROP INDEX ix_jobs_recovery"))

    async with rehearsal_engine.begin() as connection:
        await connection.run_sync(precreate)
    await _upgrade(rehearsal_engine, REVISION)

    async with rehearsal_engine.connect() as connection:
        await connection.run_sync(_assert_parity)
        assert (await connection.execute(sa.text("SELECT revision FROM job_owners WHERE owner_id = 'retained'"))).scalar_one() == 4


async def test_duplicate_legacy_memory_rolls_back_revision_and_keeps_history(rehearsal_engine) -> None:
    await _upgrade(rehearsal_engine, PREMODERNIZATION)
    async with rehearsal_engine.begin() as connection:
        tables, _ = await connection.run_sync(_seed_legacy)
        memory = next(table for table in tables if table.name == "memory_items")
        row = (await connection.execute(sa.select(memory))).mappings().one()
        await connection.execute(memory.insert().values(**{**row, "id": "duplicate-memory"}))

    with pytest.raises(RuntimeError, match="Legacy duplicates"):
        await _upgrade(rehearsal_engine, REVISION)

    async with rehearsal_engine.connect() as connection:
        assert (await connection.execute(sa.text("SELECT version_num FROM alembic_version"))).scalar_one() == PREMODERNIZATION
        assert (await connection.execute(sa.text("SELECT count(*) FROM memory_items"))).scalar_one() == 2
        assert "durable_jobs" not in await connection.run_sync(lambda sync: sa.inspect(sync).get_table_names())


async def test_postgresql_native_vector_search_filters_space_and_study(rehearsal_engine) -> None:
    await _upgrade(rehearsal_engine, PREMODERNIZATION)
    async with rehearsal_engine.begin() as connection:
        await connection.run_sync(_seed_legacy)
    await _upgrade(rehearsal_engine, REVISION)
    positive = [1.0] + [0.0] * (CANONICAL_DIM - 1)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sessions = async_sessionmaker(rehearsal_engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all([
            EvidenceChunks(id="other-study", source_id="legacy-source", study_id="different-study", content="Synthetic",
                           embedding=positive, embedding_space="db-integration-space"),
            EvidenceChunks(id="other-space", source_id="legacy-source", study_id="legacy-study", content="Synthetic",
                           embedding=positive, embedding_space="different-space"),
            EvidenceChunks(id="orthogonal", source_id="legacy-source", study_id="legacy-study", content="Synthetic",
                           embedding=[0.0, 1.0] + [0.0] * (CANONICAL_DIM - 2), embedding_space="db-integration-space"),
        ])
        await session.commit()
        backend = _RehearsalEmbedding()
        result = await VectorSearchEngine(backend).search_chunks(session, "legacy-study", "synthetic query", top_k=1)
        assert [(chunk.id, score) for chunk, score in result] == [("legacy-chunk", 1.0)]


async def test_real_tls_rejects_untrusted_ca_and_wrong_hostname(disposable_postgres, tmp_path, monkeypatch) -> None:
    target = disposable_postgres
    run = target.run
    certificate = "/var/lib/postgresql/data/integrator.crt"
    key = "/var/lib/postgresql/data/integrator.key"
    run("exec", target.container, "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-days", "1",
        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost", "-keyout", key, "-out", certificate)
    run("exec", target.container, "chown", "postgres:postgres", key, certificate)
    run("exec", target.container, "chmod", "600", key)
    for setting, value in (("ssl_cert_file", certificate), ("ssl_key_file", key), ("ssl", "on")):
        run("exec", target.container, "psql", "-U", "db_integrator", "-d", target.database, "-c", f"ALTER SYSTEM SET {setting} = '{value}'")
    run("exec", target.container, "psql", "-U", "db_integrator", "-d", target.database, "-c", "SELECT pg_reload_conf()")
    public_certificate = run("exec", target.container, "cat", certificate).stdout
    root = tmp_path / "synthetic-root.crt"
    root.write_text(public_certificate, encoding="ascii")
    for name in ("PGSSLKEY", "PGSSLCERT", "PGSSLCRL", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "SSLKEYLOGFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PGSSLROOTCERT", str(root))

    async def connect(hostname: str, mode: str, ssl_context=None) -> None:
        url = normalize_async_database_url(f"postgresql://db_integrator@{hostname}:{target.port}/{target.database}?sslmode={mode}")
        arguments = {"password": "synthetic-test-only"}
        if ssl_context is not None:
            arguments["ssl"] = ssl_context
        engine = create_async_engine(url, poolclass=sa.pool.NullPool, hide_parameters=True, connect_args=arguments)
        try:
            async with engine.connect() as connection:
                assert (await connection.execute(sa.text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"))).scalar_one() is True
        finally:
            await engine.dispose()

    await connect("localhost", "verify-full")
    await connect("127.0.0.1", "verify-ca")
    with pytest.raises(ssl.SSLCertVerificationError):
        await connect("127.0.0.1", "verify-full")
    with pytest.raises(ssl.SSLCertVerificationError):
        await connect("localhost", "verify-full", ssl.create_default_context())