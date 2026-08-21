from fastapi import APIRouter

from bebshax import __version__
from bebshax.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
    }
