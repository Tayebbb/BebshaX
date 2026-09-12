import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from pgvector.sqlalchemy import Vector

# Add apps/backend to path so we can import bebshax
sys.path.insert(0, str(Path(__file__).parent.parent))

from bebshax.config import get_settings
from bebshax.db.engine import get_metadata, normalize_async_database_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = get_metadata()


def migration_url() -> str:
    explicit_url = config.attributes.get("database_url")
    if explicit_url is not None:
        if not isinstance(explicit_url, str) or not explicit_url:
            raise ValueError("An explicit migration database_url must be a nonempty string")
        return normalize_async_database_url(explicit_url)
    return normalize_async_database_url(get_settings().database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        if context.get_context().dialect.name == "postgresql":
            context.execute("CREATE EXTENSION IF NOT EXISTS vector")
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Register pgvector type for Alembic (UPPERCASE as per pgvector-python current API)
    if connection.dialect.name == "postgresql":
        connection.dialect.ischema_names["vector"] = Vector

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        user_module_prefix="pgvector.sqlalchemy.",
        compare_type=True,
    )

    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_async_engine(
        migration_url(),
        poolclass=pool.NullPool,
        hide_parameters=True,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    connection = config.attributes.get("connection")
    if connection is not None:
        if not isinstance(connection, Connection):
            raise TypeError("The migration connection must be a SQLAlchemy Connection")
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
