"""Offline regressions for the modernization database foundation."""

import logging
import ssl
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from bebshax.db import engine as engine_module
from bebshax.db.models import Base, EvidenceChunks
from bebshax.llm.adapters.embeddings import CANONICAL_DIM


@pytest.mark.parametrize(
    "mode", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]
)
def test_asyncpg_url_preserves_ssl_verification_mode(mode: str) -> None:
    normalized = engine_module.normalize_async_database_url(
        f"postgresql://db.example.test/research?sslmode={mode}&channel_binding=require"
    )

    assert urlsplit(normalized).scheme == "postgresql+asyncpg"
    assert parse_qs(urlsplit(normalized).query) == {"ssl": [mode]}


@pytest.mark.parametrize(
    "query",
    [
        "sslmode=verify-full&ssl=require",
        "ssl=require&sslmode=verify-full",
        "sslmode=require&sslmode=verify-full",
        "sslmode=",
        "sslmode=unknown-mode",
    ],
)
def test_ambiguous_or_invalid_ssl_modes_are_rejected(query: str) -> None:
    with pytest.raises(ValueError, match="SSL mode"):
        engine_module.normalize_async_database_url(
            f"postgresql://db.example.test/research?{query}"
        )


def test_normalization_preserves_supported_asyncpg_options() -> None:
    normalized = engine_module.normalize_async_database_url(
        "postgres://db.example.test/research?sslmode=verify-full"
        "&target_session_attrs=read-write&channel_binding=require"
    )
    _, arguments = postgresql.asyncpg.dialect().create_connect_args(make_url(normalized))

    assert arguments["ssl"] == "verify-full"
    assert arguments["target_session_attrs"] == "read-write"
    assert "sslmode" not in arguments
    assert "channel_binding" not in arguments
    assert engine_module.normalize_async_database_url(normalized) == normalized


@pytest.fixture
def parse_asyncpg_ssl(monkeypatch):
    from asyncpg import connect_utils

    monkeypatch.setattr(connect_utils, "_dot_postgresql_path", lambda _: None)
    for name in ("PGSSLROOTCERT", "PGSSLCRL", "PGSSLKEY", "PGSSLCERT", "SSLKEYLOGFILE"):
        monkeypatch.delenv(name, raising=False)

    def parse(mode: str):
        normalized = engine_module.normalize_async_database_url(
            f"postgresql://db.example.test/research?sslmode={mode}"
        )
        _, arguments = postgresql.asyncpg.dialect().create_connect_args(make_url(normalized))
        _, parameters, _ = connect_utils._parse_connect_arguments(
            dsn=None, host=arguments["host"], port=5432, user="foundation_test",
            password="synthetic-test-password", passfile=None, database="research",
            command_timeout=None, statement_cache_size=100,
            max_cached_statement_lifetime=300, max_cacheable_statement_size=15360,
            ssl=arguments["ssl"], direct_tls=None, server_settings=None,
            target_session_attrs=None, krbsrvname=None, gsslib=None,
            service=None, servicefile=None,
        )
        return parameters.ssl

    return parse


@pytest.mark.parametrize("mode", ["verify-ca", "verify-full"])
def test_verified_ssl_refuses_missing_trust_roots(parse_asyncpg_ssl, mode: str) -> None:
    from asyncpg.exceptions import ClientConfigurationError

    with pytest.raises(ClientConfigurationError, match="root certificate"):
        parse_asyncpg_ssl(mode)


@pytest.mark.parametrize("mode", ["verify-ca", "verify-full"])
def test_verified_ssl_uses_ca_and_correct_hostname_policy(
    monkeypatch, tmp_path, parse_asyncpg_ssl, mode: str,
) -> None:
    ca_path = str(tmp_path / "test-only-root.crt")
    load_ca = MagicMock()
    monkeypatch.setenv("PGSSLROOTCERT", ca_path)
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", load_ca)

    context = parse_asyncpg_ssl(mode)

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is (mode == "verify-full")
    load_ca.assert_called_once_with(cafile=ca_path)


def test_evidence_cosine_comparator_compiles_native_postgresql_sql() -> None:
    distance = EvidenceChunks.embedding.cosine_distance([0.0] * CANONICAL_DIM)
    statement = select(EvidenceChunks.id).order_by(distance).limit(6)

    assert " <=> " in str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("table_name", ["evidence_chunks", "memory_items"])
def test_vector_index_metadata_matches_historical_migrations(table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    matching = [
        index for index in table.indexes
        if index.name == f"ix_{table_name}_embedding_hnsw"
    ]

    assert len(matching) == 1
    index = matching[0]
    assert list(index.columns.keys()) == ["embedding"]
    assert index.dialect_options["postgresql"]["using"] == "hnsw"
    assert index.dialect_options["postgresql"]["ops"] == {
        "embedding": "vector_cosine_ops"
    }


@pytest.mark.parametrize(
    "url", ["sqlite+aiosqlite:///:memory:", "postgresql://db.example.test/research"]
)
def test_engine_hides_bound_parameters(monkeypatch, url: str) -> None:
    factory = MagicMock()
    monkeypatch.setattr(engine_module, "create_async_engine", factory)
    settings = SimpleNamespace(
        database_url=url, environment="development", db_pool_size=5, db_max_overflow=5
    )

    engine_module.create_engine(settings)

    assert factory.call_args.kwargs.get("hide_parameters") is True


async def test_session_factory_uses_native_async_factory_with_safe_commit_settings() -> None:
    engine = engine_module.create_engine(SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:"))
    try:
        factory = engine_module.create_async_sessionmaker(engine)
        assert isinstance(factory, async_sessionmaker)
        async with factory() as session:
            assert session.bind is engine
            assert session.sync_session.expire_on_commit is False
            assert session.autoflush is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_heads",
    [(), ("behind_head",), ("unknown_head",), ("foundation_head", "other_head"), ("foundation_head",)],
)
async def test_postgresql_requires_revision_without_creating_or_stamping(
    monkeypatch, current_heads: tuple[str, ...],
) -> None:
    from alembic.runtime.migration import MigrationContext

    connection = MagicMock()
    connection.dialect.name = "postgresql"
    connection.execute = AsyncMock()
    connection.commit = AsyncMock()
    connection.run_sync = AsyncMock(side_effect=lambda callback: callback(MagicMock()))
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect.return_value.__aenter__.return_value = connection
    engine.begin.return_value.__aenter__.return_value = connection
    validate_schema = MagicMock()
    monkeypatch.setattr(engine_module, "_validate_schema", validate_schema)
    monkeypatch.setattr("sqlalchemy.inspect", lambda _: SimpleNamespace(has_table=lambda _: True))
    monkeypatch.setattr(engine_module, "_alembic_script_head", lambda: "foundation_head")
    monkeypatch.setattr(
        MigrationContext, "configure",
        lambda _: SimpleNamespace(get_current_heads=lambda: current_heads),
    )

    if current_heads == ("foundation_head",):
        await engine_module.init_database(engine, seed=False)
    else:
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            await engine_module.init_database(engine, seed=False)

    connection.execute.assert_not_awaited()
    engine.begin.assert_not_called()
    if current_heads == ("foundation_head",):
        validate_schema.assert_called_once()
    else:
        validate_schema.assert_not_called()


@pytest.mark.parametrize("drift", ["missing_table", "missing_column", "wrong_type", "missing_index", "none"])
def test_schema_validation_does_not_accept_marker_only_parity(drift: str) -> None:
    metadata = sa.MetaData()
    table = sa.Table(
        "schema_probe", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Index("ix_schema_probe_value", "value"),
    )
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            if drift == "missing_column":
                connection.execute(sa.text("CREATE TABLE schema_probe (id VARCHAR(64) NOT NULL PRIMARY KEY)"))
            elif drift == "wrong_type":
                connection.execute(sa.text(
                    "CREATE TABLE schema_probe (id VARCHAR(64) NOT NULL PRIMARY KEY, value TEXT NOT NULL)"
                ))
            elif drift != "missing_table":
                table.create(connection)
            if drift == "missing_index":
                connection.execute(sa.text("DROP INDEX ix_schema_probe_value"))

            if drift == "none":
                engine_module._validate_schema(connection, metadata)
            else:
                with pytest.raises(RuntimeError, match="schema.*Alembic"):
                    engine_module._validate_schema(connection, metadata)
    finally:
        engine.dispose()


def test_missing_script_head_is_not_silently_accepted(monkeypatch) -> None:
    from alembic.script import ScriptDirectory

    monkeypatch.setattr(
        ScriptDirectory, "from_config",
        lambda _: SimpleNamespace(get_current_head=lambda: None),
    )

    with pytest.raises(RuntimeError, match="no head"):
        engine_module._alembic_script_head()


def test_invalid_script_graph_is_not_silently_accepted(monkeypatch) -> None:
    from alembic.script import ScriptDirectory
    from alembic.util import CommandError

    monkeypatch.setattr(
        ScriptDirectory, "from_config", MagicMock(side_effect=CommandError("multiple heads"))
    )

    with pytest.raises(CommandError, match="multiple heads"):
        engine_module._alembic_script_head()


@pytest.mark.asyncio
async def test_sqlite_bootstrap_is_repeatable_without_alembic_stamp() -> None:
    settings = SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")
    engine = engine_module.create_engine(settings)
    try:
        first_tables = await engine_module.init_database(engine, seed=False)
        assert await engine_module.init_database(engine, seed=False) == first_tables
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            for table_name in ("evidence_chunks", "memory_items"):
                indexes = await connection.run_sync(
                    lambda sync, name=table_name: inspect(sync).get_indexes(name)
                )
                assert f"ix_{table_name}_embedding_hnsw" not in {
                    index["name"] for index in indexes
                }
        assert "evidence_chunks" in tables
        assert "alembic_version" not in tables
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_error_logs_hide_actual_bound_values(caplog) -> None:
    settings = SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")
    engine = engine_module.create_engine(settings)
    marker = "synthetic-sensitive-bind-value"
    try:
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine"):
            async with engine.begin() as connection:
                await connection.execute(text("CREATE TABLE redaction_probe (value TEXT UNIQUE)"))
                insert = text("INSERT INTO redaction_probe (value) VALUES (:value)")
                await connection.execute(insert, {"value": marker})
                with pytest.raises(IntegrityError) as failure:
                    await connection.execute(insert, {"value": marker})
                assert marker not in str(failure.value)
                assert "parameters hidden" in str(failure.value)
        assert marker not in caplog.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seed_failure_logs_omit_private_driver_details(monkeypatch, caplog) -> None:
    marker = "synthetic-private-bootstrap-detail"
    bootstrap = AsyncMock(side_effect=RuntimeError(marker))
    demo_seed = AsyncMock(side_effect=RuntimeError(marker))
    monkeypatch.setattr("bebshax.db.seed.ensure_shared_tenant_users", bootstrap)
    monkeypatch.setattr("bebshax.db.seed.seed_demo_data", demo_seed)
    settings = SimpleNamespace(database_url="sqlite+aiosqlite:///:memory:")
    engine = engine_module.create_engine(settings)
    sessions = engine_module.create_async_sessionmaker(engine)
    try:
        await engine_module.init_database(engine, sessions, seed=True)

        bootstrap.assert_awaited_once_with(sessions)
        demo_seed.assert_awaited_once_with(sessions)
        assert marker not in caplog.text
        assert "bootstrap failed" in caplog.text
        assert "demo data" in caplog.text.lower()
    finally:
        await engine.dispose()