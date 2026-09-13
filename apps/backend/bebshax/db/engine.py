"""Async SQLAlchemy engine and session factory for BebshaX."""

import logging
import os
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import CheckConstraint, MetaData, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bebshax.config import Settings

logger = logging.getLogger(__name__)


class SchemaValidationError(RuntimeError):
    """Startup revision/schema mismatch; messages name schema state, never connection details."""


def get_metadata() -> MetaData:
    """Register every owning feature's mappings without importing the application."""
    from bebshax.db.models import Base

    for module_name in (
        "bebshax.auth.models",
        "bebshax.behavioral.orm",
        "bebshax.datasets.orm",
        "bebshax.interview.orm",
        "bebshax.jobs.orm",
        "bebshax.memory.orm",
        "bebshax.persona.orm",
        "bebshax.personas.orm",
    ):
        import_module(module_name)
    return Base.metadata


def _alembic_ini_path() -> Path:
    """alembic.ini beside the checked-out package (editable install) or in the
    working directory (the release image installs the wheel and copies the
    scripts to WORKDIR)."""
    candidates = (Path(__file__).resolve().parents[2] / "alembic.ini", Path.cwd() / "alembic.ini")
    for candidate in candidates:
        if candidate.is_file() and (candidate.parent / "alembic").is_dir():
            return candidate
    raise SchemaValidationError(
        "alembic.ini and its scripts were found neither beside the package nor in the working directory."
    )


def _alembic_script_head() -> str:
    """Resolve the migration head from the checked-in scripts (no DB access)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini = _alembic_ini_path()
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        raise SchemaValidationError("Alembic migration scripts have no head; schema cannot be validated.")
    return head


def _validate_schema(connection: Connection, metadata: MetaData) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from pgvector.sqlalchemy import Vector

    if connection.dialect.name == "postgresql":
        connection.dialect.ischema_names = {**connection.dialect.ischema_names, "vector": Vector}
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    message = "Database schema differs from the Alembic-managed metadata; reconcile before startup."
    if compare_metadata(context, metadata):
        raise SchemaValidationError(message)
    inspector = inspect(connection)
    for table in metadata.tables.values():
        expected_checks = {
            constraint.name for constraint in table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name is not None
        }
        if expected_checks and not expected_checks <= {
            constraint["name"] for constraint in inspector.get_check_constraints(table.name, schema=table.schema)
        }:
            raise SchemaValidationError(message)
        vector_indexes = [
            index for index in table.indexes
            if index.dialect_options["postgresql"].get("using") == "hnsw"
        ]
        if connection.dialect.name == "postgresql" and vector_indexes:
            actual_indexes = {
                index["name"]: index for index in inspector.get_indexes(table.name, schema=table.schema)
            }
            for index in vector_indexes:
                actual = actual_indexes.get(index.name, {}).get("dialect_options", {})
                if (
                    actual.get("postgresql_using") != "hnsw"
                    or actual.get("postgresql_ops") != index.dialect_options["postgresql"]["ops"]
                ):
                    raise SchemaValidationError(message)


def normalize_async_database_url(url: str) -> str:
    """Use async dialects without weakening PostgreSQL SSL verification.
    
    Supports:
    - PostgreSQL (asyncpg): postgresql://, postgres://, postgresql+asyncpg://
    - SQLite (aiosqlite): sqlite://, sqlite+aiosqlite://
    - MySQL (aiomysql): mysql://, mysql+aiomysql://

    asyncpg accepts libpq SSL modes as ``ssl``, not ``sslmode`` keyword arguments.
    Channel binding is deliberately omitted because asyncpg does not implement it.
    """
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
        url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    elif url.startswith("mysql://") and not url.startswith("mysql+aiomysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)

    parsed = urlparse(url)
    if "asyncpg" in parsed.scheme and parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        ssl_values = [
            value
            for key, values in query_params.items()
            if key.lower() in ("ssl", "sslmode")
            for value in values
        ]
        if len(ssl_values) > 1:
            raise ValueError("Specify only one PostgreSQL SSL mode")
        new_query = {}
        for key, values in query_params.items():
            key_lower = key.lower()
            if key_lower in ("ssl", "sslmode"):
                mode = values[0].lower()
                if mode not in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
                    raise ValueError("Invalid PostgreSQL SSL mode")
                new_query["ssl"] = mode
            elif key_lower == "channel_binding":
                continue
            else:
                new_query[key] = values[0]
        new_query_str = urlencode(new_query)
        url = urlunparse(parsed._replace(query=new_query_str))

    return url


def create_engine(settings: Settings, url_override: Optional[str] = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine configured appropriately for the target dialect."""
    raw_url = url_override or settings.database_url
    if ("localhost" in raw_url or "127.0.0.1" in raw_url) and (os.environ.get("RENDER") or settings.environment in ("production", "staging")):
        raise RuntimeError(
            "BEBSHAX_DATABASE_URL points at localhost while running in a hosted "
            f"environment (environment={settings.environment!r}). Set BEBSHAX_DATABASE_URL "
            "to the managed Postgres connection string in the deployment environment."
        )
    db_url = normalize_async_database_url(raw_url)

    if "sqlite" in db_url:
        return create_async_engine(
            db_url,
            echo=False,
            hide_parameters=True,
            connect_args={"check_same_thread": False},
        )

    # Postgres, MySQL, or other enterprise async connection pools
    return create_async_engine(
        db_url,
        echo=False,
        hide_parameters=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_async_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session maker.

    expire_on_commit=False: prevent lazy-refresh on post-commit attribute
    access, which would raise MissingGreenlet in async contexts.
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_database(
    engine: AsyncEngine,
    sessionmaker_: Optional[Callable[[], AsyncSession]] = None,
    seed: bool = True,
) -> list[str]:
    """Validate Alembic ownership before seeding; bootstrap only isolated SQLite schemas.
    
    PostgreSQL schema changes must be applied with Alembic before startup.
    Returns the registered table names, not a claim that migrations ran here.
    """
    metadata = get_metadata()

    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)
    else:
        from alembic.runtime.migration import MigrationContext

        head = _alembic_script_head()
        async with engine.connect() as conn:
            current_heads = await conn.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_heads()
            )
            if tuple(current_heads) != (head,):
                raise SchemaValidationError(
                    "Database schema is not at the Alembic head. Run `alembic upgrade head` "
                    "before starting the application; unversioned legacy schemas require "
                    "reconciliation first."
                )
            await conn.run_sync(lambda sync_conn: _validate_schema(sync_conn, metadata))
        logger.info("Database revision and schema match the checked-in Alembic metadata")

    # 3. Shared-tenant users rows (usr_default & co.) must exist before any
    #    owner_id-stamped insert — independent of demo seeding.
    if sessionmaker_:
        try:
            from bebshax.db.seed import ensure_shared_tenant_users
            await ensure_shared_tenant_users(sessionmaker_)
        except Exception:
            logger.warning("Shared-tenant user bootstrap failed")

    # 4. Seed demo data if requested and sessionmaker is provided
    if seed and sessionmaker_:
        try:
            from bebshax.db.seed import seed_demo_data
            await seed_demo_data(sessionmaker_)
        except Exception:
            logger.warning("Demo data seeding failed")

    table_names = list(metadata.tables.keys())
    logger.info("Database schema initialized with %d tables: %s", len(table_names), table_names)
    return table_names


async def get_session(
    sessionmaker_: Callable[[], AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints."""
    async with sessionmaker_() as session:
        yield session
