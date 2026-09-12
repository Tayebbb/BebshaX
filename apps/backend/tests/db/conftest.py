"""Database test fixtures."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.engine import get_metadata


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--db-docker", action="store_true", default=False,
        help="Run DB integration tests in uniquely named disposable local Docker PostgreSQL containers only.",
    )


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite async engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(get_metadata().create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create an async session for tests."""
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    async with factory() as session:
        yield session
