"""Async SQLAlchemy engine and session factory for BebshaX."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings


from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def normalize_async_database_url(url: str) -> str:
    """Ensure PostgreSQL URLs use the asyncpg async dialect and compatible SSL query params."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    if "asyncpg" in parsed.scheme and parsed.query:
        query_params = parse_qs(parsed.query)
        new_query = {}
        for k, v in query_params.items():
            k_lower = k.lower()
            if k_lower == "sslmode":
                val = v[0].lower()
                if val in ("require", "verify-ca", "verify-full"):
                    new_query["ssl"] = "require"
            elif k_lower in ("channel_binding", "target_session_attrs"):
                continue  # asyncpg doesn't support libpq-specific channel_binding in URL
            else:
                new_query[k] = v[0]
        new_query_str = urlencode(new_query)
        url = urlunparse(parsed._replace(query=new_query_str))

    return url


def create_engine(settings: Settings) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Configuration:
    - pool_size=5, max_overflow=5: one uvicorn process on 15.7 GB laptop
    - pool_pre_ping=True: detect stale connections (pooled connections)
    - pool_recycle=1800: force reconnect every 30 min (avoid firewall timeouts)
    """
    db_url = normalize_async_database_url(settings.database_url)
    return create_async_engine(
        db_url,
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
