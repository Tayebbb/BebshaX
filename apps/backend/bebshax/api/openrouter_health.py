"""OpenRouter API health diagnostics endpoint.

Safe server-side diagnostics:
- NEVER leaks API keys or Authorization headers
- GET reports configuration only (key present? which models?) — anonymous,
  so it makes NO network call and spends nothing
- POST /test runs the real authenticated probe (auth + rate limit) and
  identifies failure kinds (auth failed, model unavailable, rate limit, timeout)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

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
    models: list[str] = Field(default_factory=list)  # routes currently offered (GET)
    status: str
    latency_ms: Optional[float] = None
    error_code: Optional[str] = None
    message: str
    verified_response: Optional[str] = None
    # Live free-catalogue discovery (routing adapter): pinned/discovered routes
    # and the last fetch error — so a drifted catalogue is visible, not guessed.
    catalogue: Optional[dict] = None


@router.get("", response_model=OpenRouterHealthResponse)
async def get_openrouter_health(request: Request) -> dict:
    """Configuration status only — no outbound call, nothing spent."""
    service = get_openrouter_service()
    report = service.configuration_report()
    routing_adapter = (getattr(request.app.state, "llm_adapters", None) or {}).get("openrouter")
    catalogue_status = getattr(routing_adapter, "catalogue_status", None)
    if callable(catalogue_status):
        catalogue = catalogue_status()
        report["catalogue"] = catalogue
        if report.get("configured"):
            report["models"] = catalogue["pinned"] or catalogue["discovered"] or report.get("models", [])
    return report


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
