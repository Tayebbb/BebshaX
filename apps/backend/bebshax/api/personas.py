"""Persona REST API: businesses, generation, retrieval, memories (Phase 8 & 9)."""

from __future__ import annotations

from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from bebshax.db.models import Businesses, Personas
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.persona.generation import PersonaGenerationFailed
from bebshax.persona.store import (
    create_business,
    get_business,
    list_businesses,
    list_personas,
    load_persona,
    save_persona,
)

router = APIRouter(tags=["personas"])


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=8000)
    industry: str | None = Field(default=None, max_length=256)
    target_market: str | None = Field(default=None, max_length=256)


class PersonaGenerateRequest(BaseModel):
    hints: str | None = Field(default=None, max_length=2000)
    generation_hints: list[str] | str | None = Field(default=None)
    audience_segment: str | None = Field(default=None, max_length=2000)


@router.post("/businesses", status_code=201)
async def create_business_endpoint(body: BusinessCreate, request: Request) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        # Include industry and target_market in description metadata if present
        desc = body.description or ""
        if body.industry or body.target_market:
            meta_parts = []
            if body.industry:
                meta_parts.append(f"Industry: {body.industry}")
            if body.target_market:
                meta_parts.append(f"Target Market: {body.target_market}")
            meta_header = " | ".join(meta_parts)
            desc = f"{meta_header}\n\n{desc}".strip()

        business = await create_business(session, body.name, desc)
    return {
        "id": business.id,
        "name": business.name,
        "description": business.description,
        "industry": body.industry or "General Enterprise",
        "target_market": body.target_market or "Global",
        "persona_count": 0,
        "created_at": business.created_at.isoformat() if business.created_at else None,
    }


@router.get("/businesses")
async def list_businesses_endpoint(request: Request) -> list[dict]:
    async with request.app.state.db_sessionmaker() as session:
        businesses = await list_businesses(session)
        # Query persona counts per business
        counts_res = await session.execute(
            select(Personas.business_id, func.count(Personas.id)).group_by(Personas.business_id)
        )
        counts_map = dict(counts_res.all())

    results = []
    for b in businesses:
        desc = b.description or ""
        industry = "General Enterprise"
        target_market = "Global"
        if desc.startswith("Industry:"):
            parts = desc.split("\n\n", 1)
            for m in parts[0].split(" | "):
                if m.startswith("Industry:"):
                    industry = m.replace("Industry:", "").strip()
                elif m.startswith("Target Market:"):
                    target_market = m.replace("Target Market:", "").strip()
            if len(parts) > 1:
                desc = parts[1]

        results.append(
            {
                "id": b.id,
                "name": b.name,
                "description": desc,
                "industry": industry,
                "target_market": target_market,
                "persona_count": counts_map.get(b.id, 0),
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
        )
    return results


@router.get("/personas")
async def list_personas_endpoint(
    request: Request, business_id: Optional[str] = Query(default=None)
) -> list[dict]:
    async with request.app.state.db_sessionmaker() as session:
        personas = await list_personas(session, business_id=business_id)
    return [p.model_dump(mode="json") for p in personas]


@router.post("/businesses/{business_id}/personas", status_code=201)
async def generate_persona_endpoint(
    business_id: str, body: PersonaGenerateRequest, request: Request
) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        business = await get_business(session, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="business not found")

    engine = request.app.state.persona_engine

    # Compose hints from audience_segment and generation_hints
    hints_list = []
    if body.audience_segment:
        hints_list.append(f"Target Audience Segment: {body.audience_segment}")
    if isinstance(body.generation_hints, list):
        hints_list.extend(body.generation_hints)
    elif isinstance(body.generation_hints, str) and body.generation_hints:
        hints_list.append(body.generation_hints)
    if body.hints:
        hints_list.append(body.hints)

    composed_hints = "\n".join(hints_list) if hints_list else None

    try:
        profile = await engine.generate(
            business_id=business.id,
            business_name=business.name,
            business_description=business.description or "",
            hints=composed_hints,
        )
    except PersonaGenerationFailed as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason": exc.reason, "violations": [v.message for v in exc.violations]},
        ) from exc
    except ContextWindowExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllCandidatesFailed as exc:
        raise HTTPException(
            status_code=503, detail="no LLM route could serve this request"
        ) from exc

    async with request.app.state.db_sessionmaker() as session:
        await save_persona(session, profile)

    # Seed initial semantic/episodic memory baseline for newly generated persona
    memory_service = getattr(request.app.state, "memory_service", None)
    if memory_service:
        try:
            await memory_service.remember(
                persona_id=profile.id,
                text=f"Identity: {profile.name}, {profile.age}yo {profile.occupation} based in {profile.location}. {profile.description}",
                kind="semantic",
                importance=0.95,
            )
            for attr in profile.attributes[:3]:
                await memory_service.remember(
                    persona_id=profile.id,
                    text=f"{attr.key}: {attr.value}",
                    kind="semantic" if attr.provenance_class.value == "OBSERVED" else "episodic",
                    importance=0.85,
                )
        except Exception:
            pass  # memory write is best-effort baseline

    return profile.model_dump(mode="json")


@router.get("/personas/{persona_id}")
async def get_persona_endpoint(persona_id: str, request: Request) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        profile = await load_persona(session, persona_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return profile.model_dump(mode="json")


@router.get("/personas/{persona_id}/memories")
async def get_persona_memories_endpoint(
    persona_id: str,
    request: Request,
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        return []

    memories = await memory_service.list_for_persona(persona_id, kind=kind, limit=limit)
    return [
        {
            "id": m.id,
            "persona_id": m.persona_id,
            "kind": m.kind,
            "text": m.text,
            "importance": m.importance,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories
    ]
