"""Liveness (`/health`) and readiness (`/health/ready`) probes.

`/health` never fails: it reports what it can see (DB reachability, local LLM
tier, provenance-sink counters) so a demo operator gets one honest snapshot.
`/health/ready` is the gate a load balancer / compose healthcheck should use —
503 until the database answers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request
from sqlalchemy import text

from bebshax import __version__
from bebshax.api.errors import APIError
from bebshax.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Covers a cold pooled connect + pre-ping to a cross-region managed Postgres
# (observed ~4s to Neon ap-southeast-1); a 2s cap false-flagged a working DB.
DB_PROBE_TIMEOUT_S = 8.0


async def probe_database(app, timeout_s: float = DB_PROBE_TIMEOUT_S) -> str:
    """``"ok"`` when ``SELECT 1`` answers within ``timeout_s``; otherwise
    ``"unreachable"`` (fail-soft: a probe must never raise)."""
    sessionmaker_ = getattr(app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        return "unreachable"

    async def _select_one() -> None:
        async with sessionmaker_() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_select_one(), timeout=timeout_s)
    except Exception as exc:  # timeout, connection refused, auth, ... all read as down
        logger.warning("health: database probe failed (%s)", type(exc).__name__)
        return "unreachable"
    return "ok"


def _sink_counters(app) -> Optional[dict[str, int]]:
    sink = getattr(app.state, "provenance_sink", None)
    if sink is None:
        return None
    return {
        "written": int(getattr(sink, "total_written", 0)),
        "dropped": int(getattr(sink, "total_dropped", 0)),
        "db_errors": int(getattr(sink, "total_db_errors", 0)),
    }


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = get_settings()
    body: dict[str, Any] = {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "db": await probe_database(request.app),
        # None until the lifespan probe has run (bare app in tests).
        "local_tier_up": getattr(request.app.state, "local_tier_up", None),
    }
    sink = _sink_counters(request.app)
    if sink is not None:
        body["sink"] = sink
    return body


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    db = await probe_database(request.app)
    if db != "ok":
        raise APIError(
            503,
            "Database unavailable — the API cannot serve requests yet.",
            error_code="database_unavailable",
            extra={"db": db},
        )
    return {"status": "ready", "db": db}
