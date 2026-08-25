"""Async SQLAlchemy engine and session factory for BebshaX."""

import logging
from typing import AsyncGenerator, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings

logger = logging.getLogger(__name__)


def normalize_async_database_url(url: str) -> str:
    """Ensure database URLs use the appropriate async dialect and compatible SSL query params.
    
    Supports:
    - PostgreSQL (asyncpg): postgresql://, postgres://, postgresql+asyncpg://
    - SQLite (aiosqlite): sqlite://, sqlite+aiosqlite://
    - MySQL (aiomysql): mysql://, mysql+aiomysql://
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


def create_engine(settings: Settings, url_override: Optional[str] = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine configured appropriately for the target dialect."""
    raw_url = url_override or settings.database_url
    db_url = normalize_async_database_url(raw_url)

    if "sqlite" in db_url:
        return create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

    # Postgres, MySQL, or other enterprise async connection pools
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


async def init_database(
    engine: AsyncEngine,
    sessionmaker_: Optional[sessionmaker[AsyncSession]] = None,
    seed: bool = True,
) -> list[str]:
    """Automatically create all tables, extensions, and seed data for the configured database.
    
    Returns the list of table names created.
    """
    # Import all ORM models so they are registered on Base.metadata
    from bebshax.auth.models import Users  # noqa: F401
    from bebshax.db.models import (  # noqa: F401
        Base,
        Businesses,
        DatasetPersonaRuns,
        DatasetSources,
        LLMRequests,
        ModelRegistry,
        Personas,
        SavedAudiences,
        Studies,
    )
    from bebshax.behavioral.orm import (  # noqa: F401
        BehavioralInsights,
        BehavioralTestResults,
        BehavioralTestRuns,
        BehavioralTestScenarios,
        BehavioralTests,
    )
    from bebshax.interview.orm import (  # noqa: F401
        Conversations,
        ConversationTurns,
        InterviewInsights,
        Interviews,
        InterviewTurns,
    )
    from bebshax.memory.orm import MemoryItems  # noqa: F401
    from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence  # noqa: F401

    # 1. Enable extensions if on PostgreSQL
    async with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                await conn.commit()
            except Exception as exc:
                logger.info("Notice: PostgreSQL vector extension: %s", exc)

    # 2. Automatically create all tables across all domains
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 3. Seed demo data if requested and sessionmaker is provided
    if seed and sessionmaker_:
        try:
            from bebshax.db.seed import seed_demo_data
            await seed_demo_data(sessionmaker_)
        except Exception as exc:
            logger.warning("Notice: Seed demo data skipped or already seeded: %s", exc)

    table_names = list(Base.metadata.tables.keys())
    logger.info("Database schema initialized with %d tables: %s", len(table_names), table_names)
    return table_names


async def get_session(
    sessionmaker_: sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI endpoints."""
    async with sessionmaker_() as session:
        yield session
