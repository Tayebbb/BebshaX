"""OpenRouter API health diagnostics endpoint.

Safe server-side diagnostics:
- NEVER leaks API keys or Authorization headers
- Tests real authenticated connection to OpenRouter
- Identifies failure kinds (missing key, auth failed, model unavailable, rate limit, timeout)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from bebshax.llm.openrouter_service import get_openrouter_service

router = APIRouter(prefix="/health/openrouter", tags=["openrouter-health"])


class OpenRouterTestRequest(BaseModel):
    model: Optional[str] = None


class OpenRouterHealthResponse(BaseModel):
    configured: bool
    authenticated: bool
    model: str
    status: str
    latency_ms: Optional[float] = None
    error_code: Optional[str] = None
    message: str
    verified_response: Optional[str] = None


@router.get("", response_model=OpenRouterHealthResponse)
async def get_openrouter_health() -> dict:
    """Check OpenRouter configuration status and availability."""
    service = get_openrouter_service()
    return await service.health_check()


@router.post("/test", response_model=OpenRouterHealthResponse)
async def test_openrouter_connection(payload: Optional[OpenRouterTestRequest] = None) -> dict:
    """Execute a live authenticated test against OpenRouter API."""
    service = get_openrouter_service()
    model = payload.model if payload else None
    return await service.health_check(model=model)
