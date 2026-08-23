"""Routes status and LLM provenance REST API endpoints."""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, Query, Request
from sqlalchemy import select, func, desc

from bebshax.db.models import LLMRequests
from bebshax.llm.pools import POOLS

router = APIRouter(tags=["routing"])


@router.get("/routes/status")
async def get_routes_status(request: Request) -> dict[str, Any]:
    """Snapshot of provider health and concurrency pool utilization."""
    adapters = getattr(request.app.state, "llm_adapters", {})
    router_instance = getattr(request.app.state, "llm_router", None)

    providers_status: list[dict[str, Any]] = []
    pools_status: list[dict[str, Any]] = []

    adapter_candidates_map: dict[str, list] = {}
    for name, adapter in adapters.items():
        type_ = "keyless"
        if "ollama" in name.lower():
            type_ = "local_fallback"
        elif "groq" in name.lower() or "openai" in name.lower() or "anthropic" in name.lower():
            type_ = "free_tier_key"

        try:
            candidates = await adapter.candidates()
        except Exception:
            candidates = []
        adapter_candidates_map[name] = candidates

        active_cooldowns = 0
        if router_instance and hasattr(router_instance, "_cooling_reason"):
            active_cooldowns = sum(
                1 for c in candidates if router_instance._cooling_reason(c) is not None
            )

        providers_status.append(
            {
                "name": name,
                "type": type_,
                "status": "healthy" if len(candidates) > 0 else "degraded",
                "available_models": len(candidates),
                "active_cooldowns": active_cooldowns,
            }
        )

    # Map pools
    for pool_name, pool_def in POOLS.items():
        candidates_count = sum(
            len(adapter_candidates_map.get(a_name, [])) for a_name in pool_def.adapters
        )
        max_concurrency = pool_def.max_concurrency
        pools_status.append(
            {
                "name": pool_name,
                "max_concurrency": max_concurrency,
                "active_requests": 0,
                "candidates_count": max(candidates_count, 1),
            }
        )

    return {
        "providers": providers_status,
        "pools": pools_status,
    }


@router.get("/provenance")
async def get_provenance(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    task: Optional[str] = Query(default=None),
    pool: Optional[str] = Query(default=None),
    persona_id: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
) -> dict[str, Any]:
    """Query recent LLM provenance records from persistence sink."""
    sessionmaker_ = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker_:
        return {"items": [], "total": 0}

    async with sessionmaker_() as session:
        query = select(LLMRequests).order_by(desc(LLMRequests.created_at))

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

        rows = (await session.execute(query.limit(limit))).scalars().all()

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
                    "attempts": r.attempts or [],
                    "served_by_provider": r.served_by_provider,
                    "served_by_model": r.response_model or r.request_model,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "total_latency_ms": r.total_latency_ms,
                    "success": r.success,
                }
            )

        return {"items": items, "total": total}
