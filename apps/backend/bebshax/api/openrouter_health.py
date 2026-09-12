"""OpenRouter API health diagnostics endpoint.

Safe server-side diagnostics:
- NEVER leaks API keys or Authorization headers
- GET reports configuration only (key present? which models?) — anonymous,
  so it makes NO network call and spends nothing
- POST /test runs the real authenticated probe (auth + rate limit) and
  identifies failure kinds (auth failed, model unavailable, rate limit, timeout)
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from bebshax.api.auth import get_current_user
from bebshax.api.errors import APIError
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.llm.governance import LLMRequestContext, llm_request_context
from bebshax.llm.openrouter_service import OpenRouterService
from bebshax.tenancy_context import tenant_scope

router = APIRouter(prefix="/health/openrouter", tags=["openrouter-health"])


class OpenRouterTestRequest(BaseModel):
    model: Optional[str] = Field(default=None, min_length=1, max_length=256, pattern=r"^\S+$")


class OpenRouterHealthResponse(BaseModel):
    configured: bool
    authenticated: bool
    model: str
    models: list[str] = Field(default_factory=list)  # routes currently offered (GET)
    status: Literal["configured", "available", "degraded", "unknown"]
    latency_ms: Optional[float] = None
    error_code: Optional[str] = None
    message: str
    verified_response: Optional[str] = None
    provider: Optional[str] = None
    request_id: Optional[str] = None
    streaming_mode: Optional[Literal["native", "buffered"]] = None
    # Live free-catalogue discovery (routing adapter): pinned/discovered routes
    # and the last fetch error — so a drifted catalogue is visible, not guessed.
    catalogue: Optional[dict] = None


_DIAGNOSTIC_STATUS = {
    "configured": "configured", "healthy": "available", "error": "degraded",
    "not_configured": "unknown", "unverified": "unknown",
}


def _normalize_report(report: dict, adapter) -> dict:
    result = dict(report)
    result["status"] = _DIAGNOSTIC_STATUS.get(report.get("status"), "unknown")
    if result["status"] == "available" and not report.get("authenticated"):
        result["status"] = "unknown"
    result["streaming_mode"] = getattr(adapter, "streaming_mode", None)
    catalogue_status = getattr(adapter, "catalogue_status", None)
    if callable(catalogue_status):
        catalogue = catalogue_status()
        result["catalogue"] = {
            "discovery_enabled": catalogue.get("discovery_enabled"),
            "pinned": catalogue.get("pinned", []),
            "discovered": catalogue.get("discovered", []),
            "fetched_at": catalogue.get("fetched_at"),
            "error": "catalogue_unavailable" if catalogue.get("error") else None,
        }
        if catalogue.get("error") and result["status"] == "configured":
            result["status"] = "degraded"
    return result


@router.get("", response_model=OpenRouterHealthResponse)
async def get_openrouter_health(request: Request) -> dict:
    """Configuration status only — no outbound call, nothing spent."""
    adapter = (getattr(request.app.state, "llm_adapters", None) or {}).get("openrouter")
    if adapter is None or not callable(getattr(adapter, "configuration_status", None)):
        return {
            "configured": False, "authenticated": False, "model": "unknown", "models": [],
            "status": "unknown", "error_code": "RUNTIME_NOT_READY",
            "message": "The shared OpenRouter adapter is not initialized.",
        }
    return _normalize_report(OpenRouterService(adapter).configuration_report(), adapter)


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
    adapter = (getattr(request.app.state, "llm_adapters", None) or {}).get("openrouter")
    llm_service = getattr(request.app.state, "llm_service", None)
    if adapter is None or llm_service is None:
        raise APIError(503, "The diagnostic runtime is not ready.", error_code="runtime_not_ready")
    service = OpenRouterService(adapter)
    model = payload.model if payload else None
    context = LLMRequestContext(owner_user_id=current_user.id, data_classification="synthetic")
    with tenant_scope(current_user.id), llm_request_context(context):
        report = await service.health_check(model=model, llm_service=llm_service)
    return _normalize_report(report, adapter)
