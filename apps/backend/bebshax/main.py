"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from bebshax import __version__
from bebshax.api.health import router as health_router
from bebshax.config import get_settings
from bebshax.llm.adapters.factory import build_default_adapters
from bebshax.llm.router import PoolRouter


@asynccontextmanager
async def _lifespan(app: FastAPI):
    adapters = build_default_adapters()  # lazy clients — no network at startup
    app.state.llm_adapters = adapters
    app.state.llm_router = PoolRouter(adapters)
    yield
    for adapter in adapters.values():
        await adapter.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=_lifespan)
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
