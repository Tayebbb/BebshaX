"""Routes status and LLM provenance REST API endpoints."""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func, desc

from bebshax.api.deps import get_tenant_user as get_current_user, require_development_diagnostics
from bebshax.api.health import provider_status_snapshot
from bebshax.auth.models import Users
from bebshax.auth.transport import AuthRoute
from bebshax.db.models import LLMRequests
from bebshax.llm.pools import POOLS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["routing"], route_class=AuthRoute)

# M2: adapter kind is registry data, not substring guessing. Unknown → "unknown".
_ADAPTER_KIND = {
    "freellmpool": "aggregator",  # one adapter fronting many providers
    "openrouter": "remote_api",
}


@router.get("/routes/status", dependencies=[Depends(require_development_diagnostics)])
async def get_routes_status(request: Request) -> dict[str, Any]:
    """Snapshot of provider health and concurrency pool utilization.

    M2 honesty rules: no invented counts (empty pools report 0), no guessed
    provider types, no private router internals — only public APIs.
    """
    adapters = getattr(request.app.state, "llm_adapters", {})
    router_instance = getattr(request.app.state, "llm_router", None)

    providers_status: list[dict[str, Any]] = []
    pools_status: list[dict[str, Any]] = []
    observations = {row["name"]: row for row in provider_status_snapshot(request.app)}

    adapter_candidates_map: dict[str, list] = {}
    for name, adapter in adapters.items():
        discovery_failed = False
        try:
            candidates = await adapter.candidates()
        except Exception:
            logger.warning("adapter %r discovery failed; reporting unavailable", name)
            candidates = []
            discovery_failed = True
        adapter_candidates_map[name] = candidates

        # None = router not wired — same honest-absence convention as active_requests
        active_cooldowns = None
        non_cooling = None
        if router_instance is not None and hasattr(router_instance, "is_cooling"):
            non_cooling = [candidate for candidate in candidates if not router_instance.is_cooling(candidate)]
            active_cooldowns = len(candidates) - len(non_cooling)

        available_models = None
        if not candidates or non_cooling == []:
            available_models = 0
        elif non_cooling is not None and not any(candidate.model in {"auto", "unknown", "*"} for candidate in non_cooling):
            available_models = sum(candidate.context_window > 0 for candidate in non_cooling)
        observation = observations[name]
        status = observation["status"]
        if discovery_failed or (available_models == 0 and (candidates or observation["configured"])):
            status = "unavailable"

        providers_status.append(
            {
                **observation,
                "type": _ADAPTER_KIND.get(name, "unknown"),
                "status": status,
                "available_models": available_models,
                "candidate_count": len(candidates),
                "active_cooldowns": active_cooldowns,
            }
        )

    utilization: dict[str, dict[str, int]] = {}
    if router_instance is not None and hasattr(router_instance, "pool_utilization"):
        utilization = router_instance.pool_utilization()

    for pool_name, pool_def in POOLS.items():
        candidates_count = sum(
            len(adapter_candidates_map.get(a_name, [])) for a_name in pool_def.adapters
        )
        pools_status.append(
            {
                "name": pool_name,
                "max_concurrency": pool_def.max_concurrency,
                # None = router not wired (honest absence), never a made-up 0
                "active_requests": utilization.get(pool_name, {}).get("active_requests"),
                "candidates_count": candidates_count,
            }
        )

    return {
        "providers": providers_status,
        "pools": pools_status,
    }


@router.get("/routing/capacity", dependencies=[Depends(require_development_diagnostics)])
async def get_routing_capacity(request: Request) -> dict[str, Any]:
    """AI plan §10: per-provider free-tier consumption vs published caps."""
    ledger = getattr(request.app.state, "quota_ledger", None)
    if ledger is None:
        return {"providers": [], "note": "quota ledger not wired"}
    router_instance = getattr(request.app.state, "llm_router", None)
    utilization = (
        router_instance.pool_utilization()
        if router_instance is not None and hasattr(router_instance, "pool_utilization")
        else {}
    )
    return {
        "providers": ledger.snapshot(),
        "pools": utilization,
    }


def redact_attempts(attempts: list[Any]) -> list[Any]:
    """Drop ``failure_detail`` (raw provider error bodies can echo request
    fragments) while keeping the classified ``failure_kind``."""
    redacted: list[Any] = []
    for attempt in attempts or []:
        if isinstance(attempt, dict) and "failure_detail" in attempt:
            attempt = {**attempt, "failure_detail": None}
        redacted.append(attempt)
    return redacted


@router.get("/provenance")
async def get_provenance(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    task: Optional[str] = Query(default=None, min_length=1, max_length=64),
    pool: Optional[str] = Query(default=None, min_length=1, max_length=64),
    persona_id: Optional[str] = Query(default=None, min_length=1, max_length=64),
    success: Optional[bool] = Query(default=None),
    current_user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    """Read only request-time ownership; unknown historical owners are never public."""
    sessionmaker_ = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker_:
        return {"items": [], "total": 0}

    async with sessionmaker_() as session:
        query = select(LLMRequests).where(LLMRequests.owner_id == current_user.id)

        if task:
            query = query.where(LLMRequests.task == task)
        if pool:
            query = query.where(LLMRequests.pool == pool)
        if persona_id:
            query = query.where(LLMRequests.persona_id == persona_id)
        if success is not None:
            query = query.where(LLMRequests.success == success)

        total_stmt = select(func.count()).select_from(query.subquery())
        total = (await session.execute(total_stmt)).scalar_one_or_none() or 0

        rows = (await session.scalars(query.order_by(desc(LLMRequests.created_at), LLMRequests.request_id).limit(limit))).all()

        items = []
        for r in rows:
            items.append(
                {
                    "request_id": r.request_id,
                    "task": r.task.value if hasattr(r.task, "value") else str(r.task),
                    "pool": r.pool,
                    "persona_id": r.persona_id,
                    "conversation_id": r.conversation_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "routing_path": r.routing_path or [],
                    "attempts": redact_attempts(r.attempts or []),
                    "served_by_provider": r.served_by_provider,
                    "served_by_model": r.response_model or "unknown",
                    "requested_model": r.request_model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "total_latency_ms": r.total_latency_ms,
                    "success": r.success,
                }
            )

        return {"items": items, "total": total}
