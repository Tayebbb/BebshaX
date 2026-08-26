"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    adapters = build_default_adapters()  # lazy clients — no network at startup
    db_engine = create_engine(settings)  # lazy — connects on first use
    sessionmaker_ = create_async_sessionmaker(db_engine)
    sink = ProvenanceSink(sessionmaker_)  # fail-soft: DB issues never fail LLM calls
    await sink.start()
    llm_router = PoolRouter(adapters, on_provenance=sink)
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

    # Automatic table creation, extensions, and demo data initialization on startup
    try:
        await init_database(db_engine, sessionmaker_, seed=True)
    except Exception:
        pass  # best-effort on startup (handles offline / cold DB)

    yield
    await sink.stop()
    for adapter in adapters.values():
        await adapter.aclose()
    await db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=_lifespan)

    # M6: explicit origins only — "*" with allow_credentials=True is spec-invalid
    # and would let any site ride a user's credentials. Origins come from settings.
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

