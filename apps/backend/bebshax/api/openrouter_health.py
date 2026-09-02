"""OpenRouter API health diagnostics endpoint.

Safe server-side diagnostics:
- NEVER leaks API keys or Authorization headers
- Tests real authenticated connection to OpenRouter
- Identifies failure kinds (missing key, auth failed, model unavailable, rate limit, timeout)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from bebshax.api.auth import get_current_user
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
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
@limiter.limit("10/hour")
async def test_openrouter_connection(
    request: Request,
    payload: Optional[OpenRouterTestRequest] = None,
    current_user: Users = Depends(get_current_user),
) -> dict:
    """Execute a live authenticated test against OpenRouter API.

    Spends a real outbound LLM call, so it carries the same auth + limit
    posture as the other budget-spending endpoints.
    """
    service = get_openrouter_service()
    model = payload.model if payload else None
    return await service.health_check(model=model)
