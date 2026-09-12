"""Liveness (`/health`) and readiness (`/health/ready`) probes.

`/health` reports DB reachability, optional capabilities and observed remote
status without spending LLM tokens or triggering provider discovery.
`/health/ready` is the gate a load balancer / compose healthcheck should use —
503 until the database answers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request
from sqlalchemy import text

from bebshax import __version__
from bebshax.api.errors import APIError
from bebshax.config import get_settings
from bebshax.llm.provenance import ProvenanceRecord

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Covers a cold pooled connect + pre-ping to a cross-region managed Postgres
# (observed ~4s to Neon ap-southeast-1); a 2s cap false-flagged a working DB.
DB_PROBE_TIMEOUT_S = 8.0
PROVIDER_OBSERVATION_MAX_AGE_S = 300.0


def record_provider_observations(app, record: ProvenanceRecord) -> None:
    """Remember the newest non-cached attempt per configured adapter slot."""
    adapters = getattr(app.state, "llm_adapters", {})
    observations = getattr(app.state, "provider_health", {})
    for attempt in record.attempts:
        if attempt.cached or "served from freellmpool response cache" in attempt.notes:
            continue
        if attempt.observations and not any(
            observation.outcome not in {"cached", "skipped"} and observation.consumption != "none"
            for observation in attempt.observations
        ):
            continue
        slot = (attempt.via or "").split("/", 1)[0] or attempt.provider
        if slot not in adapters:
            continue
        observed_at = attempt.started_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        previous = observations.get(slot)
        if previous is None or previous["observed_at"] <= observed_at:
            observations[slot] = {"observed_at": observed_at, "success": attempt.success}
    app.state.provider_health = observations


def provider_status_snapshot(app) -> list[dict[str, Any]]:
    """Public, network-free adapter snapshot for fleet-health consumers."""
    rows = []
    observations = getattr(app.state, "provider_health", {})
    now = datetime.now(timezone.utc)
    for name, adapter in getattr(app.state, "llm_adapters", {}).items():
        configured = None
        status = "unknown"
        configuration_status = getattr(adapter, "configuration_status", None)
        if callable(configuration_status):
            try:
                configuration = configuration_status()
                configured = configuration.get("configured")
                status = "configured" if configured else "unknown"
            except Exception:
                status = "degraded"
        catalogue_status = getattr(adapter, "catalogue_status", None)
        if callable(catalogue_status):
            try:
                if catalogue_status().get("error"):
                    status = "degraded"
            except Exception:
                status = "degraded"
        observation = observations.get(name)
        recent = observation is not None and 0 <= (now - observation["observed_at"]).total_seconds() <= PROVIDER_OBSERVATION_MAX_AGE_S
        if recent:
            status = "available" if observation["success"] else "degraded"
        rows.append({
            "name": name, "status": status, "configured": configured,
            "streaming_mode": getattr(adapter, "streaming_mode", None),
            "recent_success": bool(recent and observation["success"]),
            "last_observed_at": observation["observed_at"].isoformat() if observation else None,
        })
    return rows


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
        "pending": sink.queue.qsize() if hasattr(sink, "queue") else 0,
        "retained_failures": len(getattr(sink, "failed_records", {})),
    }


async def _persona_status(app) -> dict[str, Any]:
    snapshot = getattr(app.state, "persona_capability_snapshot", None)
    if callable(snapshot):
        try:
            return await snapshot()
        except Exception:
            return {"status": "unavailable", "reason": "artifact_unavailable"}
    return getattr(app.state, "persona_capability", {"status": "unknown", "reason": "runtime_not_ready"})


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = get_settings()
    providers = provider_status_snapshot(request.app)
    persona = await _persona_status(request.app)
    chat_status = "unknown"
    if any(provider["status"] == "available" for provider in providers):
        chat_status = "available"
    elif any(provider["status"] == "degraded" for provider in providers):
        chat_status = "degraded"
    elif any(provider["status"] == "configured" for provider in providers):
        chat_status = "configured"
    body: dict[str, Any] = {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "environment": settings.environment,
        "demo_mode": settings.demo_mode,
        "db": await probe_database(request.app),
        "core_ready": bool(getattr(request.app.state, "core_ready", False)),
        "schema_validated": bool(getattr(request.app.state, "database_revision_validated", False)),
        "providers": providers,
        "capabilities": {
            "chat": {"status": chat_status},
            "persona_generation": persona,
            "memory_embeddings": {"status": "configured", "backend": settings.embedding_backend},
        },
    }
    policy = getattr(request.app.state, "remote_processing_policy", None)
    if policy is not None:
        body["remote_processing"] = {
            "policy_id": policy.policy_id,
            "private_providers": sorted(policy.private_providers),
            "synthetic_providers": sorted(policy.synthetic_providers),
            "explicit": policy.policy_id != "configured-providers-default",
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
    if not getattr(request.app.state, "core_ready", False) or not getattr(request.app.state, "database_revision_validated", False):
        raise APIError(503, "Application startup validation is incomplete.", error_code="runtime_not_ready", extra={"db": db})
    persona = await _persona_status(request.app)
    if getattr(request.app.state, "persona_required", False) and persona["status"] not in {"configured", "available"}:
        raise APIError(503, "Required persona capability is unavailable.", error_code="ml_persona_unavailable", extra={"db": db})
    return {"status": "ready", "db": db}
