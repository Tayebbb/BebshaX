"""Async SQLAlchemy engine and session factory for BebshaX."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Configuration:
    - pool_size=5, max_overflow=5: one uvicorn process on 15.7 GB laptop
    - pool_pre_ping=True: detect stale connections (pooled connections)
    - pool_recycle=1800: force reconnect every 30 min (avoid firewall timeouts)
    """
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_async_sessionmaker(engine: AsyncEngine) -> sessionmaker[AsyncSession]:
    """Create an async session maker.

    expire_on_commit=False: prevent lazy-refresh on post-commit attribute
    access, which would raise MissingGreenlet in async contexts.
    """
    return sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )


async def get_session(
    sessionmaker_: sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints."""
    async with sessionmaker_() as session:
        yield session
