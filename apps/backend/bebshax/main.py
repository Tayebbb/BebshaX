"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from bebshax.api.limiter import limiter



from bebshax import __version__
from bebshax.api.auth import auth_router
from bebshax.api.copilot import router as copilot_router
from bebshax.api.evaluation import router as evaluation_router
from bebshax.api.health import router as health_router
from bebshax.api.interviews import router as interviews_router
from bebshax.api.personas import router as personas_router
from bebshax.api.routes import router as routes_router
from bebshax.api.studies import router as studies_router
from bebshax.auth.models import Users
from bebshax.config import get_settings
from bebshax.db.engine import create_async_sessionmaker, create_engine, init_database
from bebshax.db.models import Base, Businesses, LLMRequests, ModelRegistry, Personas, SavedAudiences, Studies
from bebshax.db.sink import ProvenanceSink
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm.adapters.base import ProviderAdapter
from bebshax.llm.adapters.factory import (
    build_default_adapters,
    build_embedding_backend,
)
from bebshax.llm.router import PoolRouter
from bebshax.memory.service import MemoryService
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.generation import PersonaEngine
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence

logger = logging.getLogger(__name__)


async def warn_if_local_tier_down(adapters: Mapping[str, ProviderAdapter]) -> bool:
    """H2: the emergency pool is local-first — losing Ollama must be loud, not silent.

    Returns True when the local tier is up (has ≥1 route).
    """
    ollama = adapters.get("ollama")
    if ollama is None:
        logger.warning("local tier: no 'ollama' adapter registered — EMERGENCY_FALLBACK has no local route")
        return False
    try:
        candidates = await ollama.candidates()
    except Exception as exc:  # candidates() is defensive, but never let startup die here
        logger.warning("local tier: Ollama candidate discovery failed (%s)", exc)
        return False
    if not candidates:
        logger.warning(
            "local tier DOWN: Ollama daemon unreachable or has no models — "
            "EMERGENCY_FALLBACK has no local route and the offline drill will fail. "
            "Start it with `ollama serve`."
        )
        return False
    logger.info("local tier up: %d Ollama model(s) available", len(candidates))
    return True



from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine
from bebshax.db.engine import normalize_async_database_url


async def check_migrations_current_async(database_url: str, alembic_ini_path: str = "alembic.ini") -> None:
    """
    Fail-fast guard: refuse to serve requests against a database that isn't
    at the current migration head. Mirrors the CI check (H6) but runs locally
    so a stale dev DB produces one clear message instead of a cryptic 500 on
    the first request that touches a missing column/table.
    """
    import os
    import sys

    if not os.path.exists(alembic_ini_path):
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"),
            os.path.join(os.getcwd(), "apps", "backend", "alembic.ini"),
            os.path.join(os.getcwd(), "alembic.ini"),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                alembic_ini_path = cand
                break

    alembic_cfg = Config(alembic_ini_path)
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revisions = set(script.get_heads())

    async_url = normalize_async_database_url(database_url)
    engine = create_async_engine(async_url)

    def _get_current(sync_conn):
        ctx = MigrationContext.configure(sync_conn)
        return set(ctx.get_current_heads())

    async with engine.connect() as conn:
        current_revisions = await conn.run_sync(_get_current)
    await engine.dispose()

    if current_revisions != head_revisions:
        print(
            "FATAL: local database is not at the current migration head.\n"
            f"  Database is at:  {current_revisions or '(no migrations applied)'}\n"
            f"  Code expects:    {head_revisions}\n"
            "  Run: alembic upgrade head\n",
            file=sys.stderr,
        )
        raise SystemExit(1)


def check_migrations_current(sync_database_url: str, alembic_ini_path: str = "alembic.ini") -> None:
    """Sync wrapper for tests and external scripts."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Fallback if called inside an event loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(asyncio.run, check_migrations_current_async(sync_database_url, alembic_ini_path)).result()
    else:
        asyncio.run(check_migrations_current_async(sync_database_url, alembic_ini_path))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()

    # Local development migration drift check (H6)
    if settings.environment in ("development", "local") and not settings.demo_mode and "localhost" in settings.database_url:
        try:
            await check_migrations_current_async(settings.database_url)
        except SystemExit:
            raise
        except Exception:
            logger.warning("Local migration check failed or skipped", exc_info=True)

    adapters = build_default_adapters()  # lazy clients — no network at startup
    db_engine = create_engine(settings)  # lazy — connects on first use
    sessionmaker_ = create_async_sessionmaker(db_engine)
    sink = ProvenanceSink(sessionmaker_)  # fail-soft: DB issues never fail LLM calls
    await sink.start()



    # AI plan §10: quota ledger (seeded from today's rows) + quota-aware ranking
    # + cooldowns that survive restarts. All fail-soft — capacity features must
    # never take the request path down.
    from bebshax.db.capacity_state import CooldownStore, load_todays_consumption
    from bebshax.llm.quota import QuotaLedger, quota_aware_ranker

    ledger = QuotaLedger()
    seed_requests, seed_tokens = await load_todays_consumption(sessionmaker_)
    ledger.seed(seed_requests, seed_tokens)
    cooldown_store = CooldownStore(sessionmaker_)
    initial_cooldowns = await cooldown_store.load_active()

    def _on_provenance(record):
        try:
            ledger.record(record)
        except Exception:
            logger.warning("quota ledger record failed", exc_info=True)
        sink(record)  # unconditional — ledger problems must never cost provenance

    llm_router = PoolRouter(
        adapters,
        on_provenance=_on_provenance,
        ranker=quota_aware_ranker(ledger),
        initial_cooldowns=initial_cooldowns,
        on_cooldown_change=cooldown_store.persist,
    )
    app.state.quota_ledger = ledger
    app.state.local_tier_up = await warn_if_local_tier_down(adapters)

    app.state.llm_adapters = adapters
    app.state.llm_router = llm_router
    app.state.llm_service = llm_router  # same object; studies/personas/evidence/segmentation resolve this name
    app.state.db_sessionmaker = sessionmaker_
    app.state.provenance_sink = sink
    app.state.persona_engine = PersonaEngine(llm_router, EvidenceStore())
    app.state.memory_service = MemoryService(
        sessionmaker_,
        build_embedding_backend(settings.embedding_backend, settings.embedding_model),
        llm=llm_router,
    )
    app.state.interview_engine = InterviewEngine(
        llm_router, sessionmaker_, memory=app.state.memory_service
    )
    from bebshax.behavioral.engine import BehavioralSimulationEngine
    app.state.behavioral_engine = BehavioralSimulationEngine(
        llm_router, sessionmaker_, memory=app.state.memory_service
    )

    # Automatic bootstrap for EMPTY databases only; alembic owns real schema
    # evolution (see docs/DATABASE_MIGRATION.md). Demo seed is opt-in (H3/M8).
    try:
        await init_database(db_engine, sessionmaker_, seed=settings.demo_mode)
    except Exception:
        logger.warning("init_database failed at startup (offline/cold DB?)", exc_info=True)

    yield
    await sink.stop()
    for adapter in adapters.values():
        await adapter.aclose()
    await db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=_lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router)
    app.include_router(routes_router, prefix="/api")
    app.include_router(personas_router, prefix="/api")
    app.include_router(interviews_router, prefix="/api")
    from bebshax.api.behavioral import router as behavioral_router
    app.include_router(behavioral_router, prefix="/api")
    app.include_router(copilot_router, prefix="/api")
    app.include_router(studies_router, prefix="/api")
    app.include_router(evaluation_router, prefix="/api")

    # OpenRouter health verification & Dataset Sources
    from bebshax.api.datasets import router as datasets_router
    from bebshax.api.openrouter_health import router as openrouter_health_router
    from bebshax.api.evidence import router as evidence_router
    from bebshax.api.segmentation import router as segmentation_router

    app.include_router(openrouter_health_router, prefix="/api")
    app.include_router(datasets_router, prefix="/api")
    app.include_router(evidence_router, prefix="/api")
    app.include_router(segmentation_router, prefix="/api")
    return app


app = create_app()

