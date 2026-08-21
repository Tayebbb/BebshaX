"""FastAPI application entry point: `uvicorn bebshax.main:app`."""

from fastapi import FastAPI

from bebshax import __version__
from bebshax.api.health import router as health_router
from bebshax.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__)
    app.include_router(health_router, prefix="/api")
    return app


app = create_app()
