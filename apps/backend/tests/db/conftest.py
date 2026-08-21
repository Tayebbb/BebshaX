"""Database test fixtures."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings
from bebshax.db.models import Base


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite async engine for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create an async session for tests."""
    async_sessionmaker = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_sessionmaker() as session:
        yield session


def settings():
    """Return test settings."""
    return Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )
