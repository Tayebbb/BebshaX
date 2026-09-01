"""Async SQLAlchemy engine and session factory for BebshaX."""

import logging
import os
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings

logger = logging.getLogger(__name__)


def _alembic_script_head() -> Optional[str]:
    """Resolve the migration head from the checked-in scripts (no DB access)."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        cfg = Config(str(ini))
        cfg.set_main_option("script_location", str(ini.parent / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        logger.warning("could not resolve alembic script head for stamping", exc_info=True)
        return None


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
        DatasetCandidates,
        DatasetPersonaRuns,
        DatasetSources,
        EvidenceChunks,
        EvidenceClaims,
        EvidenceSources,
        LLMRequests,
        MarketSegments,
        ModelRegistry,
        PersonaGenerationRuns,
        Personas,
        ResearchPlans,
        ResearchRuns,
        SavedAudiences,
        SegmentationRuns,
        Studies,
        StudyReports,
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

    # 2. Schema: alembic is the single source of truth (docs/DATABASE_MIGRATION.md).
    #    create_all is a BOOTSTRAP for empty databases only — and is stamped so
    #    later `alembic upgrade head` runs cleanly instead of fighting create_all.
    def _inspect_state(sync_conn):
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(sync_conn)
        return insp.has_table("alembic_version"), insp.has_table("businesses")

    async with engine.connect() as conn:
        alembic_managed, has_app_schema = await conn.run_sync(_inspect_state)

    if alembic_managed:
        logger.info("alembic_version present — schema owned by alembic; skipping create_all")
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            head = _alembic_script_head()
            if not has_app_schema and head:
                # Fresh database: record the head so alembic and create_all agree.
                await conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS alembic_version ("
                        "version_num VARCHAR(32) NOT NULL, "
                        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                    )
                )
                await conn.execute(text("DELETE FROM alembic_version"))
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head}
                )
                logger.info("fresh database bootstrapped via create_all and stamped at %s", head)
            elif has_app_schema:
                logger.warning(
                    "legacy create_all schema without alembic_version detected — "
                    "missing tables were created but the revision was NOT stamped; "
                    "reconcile manually with `alembic stamp <revision>`"
                )

    # 3. Shared-tenant users rows (usr_default & co.) must exist before any
    #    owner_id-stamped insert — independent of demo seeding.
    if sessionmaker_:
        try:
            from bebshax.db.seed import ensure_shared_tenant_users
            await ensure_shared_tenant_users(sessionmaker_)
        except Exception:
            logger.warning("shared-tenant user bootstrap failed", exc_info=True)

    # 4. Seed demo data if requested and sessionmaker is provided
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
