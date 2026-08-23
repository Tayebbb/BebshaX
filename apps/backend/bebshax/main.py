"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from bebshax import __version__
from bebshax.api.health import router as health_router
from bebshax.api.personas import router as personas_router
from bebshax.config import get_settings
from bebshax.db.engine import create_async_sessionmaker, create_engine
from bebshax.db.sink import ProvenanceSink
from bebshax.llm.adapters.factory import (
    build_default_adapters,
    build_embedding_backend,
)
from bebshax.llm.router import PoolRouter
from bebshax.memory.service import MemoryService
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.generation import PersonaEngine


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    adapters = build_default_adapters()  # lazy clients — no network at startup
    db_engine = create_engine(settings)  # lazy — connects on first use
    sessionmaker_ = create_async_sessionmaker(db_engine)
    sink = ProvenanceSink(sessionmaker_)  # fail-soft: DB issues never fail LLM calls
    await sink.start()
    llm_router = PoolRouter(adapters, on_provenance=sink)

    app.state.llm_adapters = adapters
    app.state.llm_router = llm_router
    app.state.db_sessionmaker = sessionmaker_
    app.state.provenance_sink = sink
    app.state.persona_engine = PersonaEngine(llm_router, EvidenceStore())
    app.state.memory_service = MemoryService(
        sessionmaker_,
        build_embedding_backend(settings.embedding_backend, settings.embedding_model),
        llm=llm_router,
    )
    yield
    await sink.stop()
    for adapter in adapters.values():
        await adapter.aclose()
    await db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=_lifespan)
    app.include_router(health_router, prefix="/api")
    app.include_router(personas_router, prefix="/api")
    return app


app = create_app()
