"""Persona REST API: study-scoped synthetic persona generation, retrieval, and legacy compatibility."""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.studies import _user_owns_study, get_session
from bebshax.auth.models import Users
from bebshax.db.models import Businesses, MarketSegments, PersonaGenerationRuns, Personas, Studies
from bebshax.db.models import DATA_SOURCE_LIVE
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
from bebshax.personas.service import PersonaGenerationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["personas"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=8000)
    industry: str | None = Field(default=None, max_length=256)
    target_market: str | None = Field(default=None, max_length=256)


class PersonaGenerateRequest(BaseModel):
    hints: str | None = Field(default=None, max_length=2000)
    generation_hints: list[str] | str | None = Field(default=None)
    audience_segment: str | None = Field(default=None, max_length=2000)


class StudyGeneratePersonasRequest(BaseModel):
    segmentation_run_id: Optional[str] = None
    personas_per_segment: Optional[int] = Field(None, ge=1, le=10)
    target_count: Optional[int] = Field(None, ge=1, le=50)
    distribution_strategy: str = Field("population_weighted", pattern="^(population_weighted|equal)$")


# ---------------------------------------------------------------------------
# Helper Serializers
# ---------------------------------------------------------------------------

def _serialize_persona(p: Personas, segment_name: Optional[str] = None) -> dict[str, Any]:
    detailed = getattr(p, "detailed_attributes", {}) or {}
    commercial = p.commercial_profile or {}
    domain_attrs = detailed.get("domain_attributes", {})
    constraints = detailed.get("constraints") or commercial.get("constraints", {})

    return {
        "id": p.id,
        "study_id": p.study_id,
        "user_id": p.user_id,
        "segment_id": p.segment_id,
        "segment_name": segment_name,
        "generation_run_id": p.generation_run_id,
        "name": p.name,
        "status": p.status,
        "version": p.version,
        "generation_model": p.generation_model,
        # H3 piece 2 — "live" | "cached", see docs/DEMO.md §4.
        "data_source": getattr(p, "data_source", DATA_SOURCE_LIVE) or DATA_SOURCE_LIVE,
        "archetype": p.archetype,
        "tagline": getattr(p, "tagline", None),
        "country_code": getattr(p, "country_code", "BD") or "BD",
        "personality": getattr(p, "personality", {}) or {},
        "detailed_attributes": detailed,
        "domain_attributes": domain_attrs,
        "constraints": constraints,
        "demographics": p.demographics or {},
        "bio": p.bio,
        "quote": p.quote,
        "goals": p.goals or [],
        "needs": p.needs or [],
        "pain_points": p.pain_points or [],
        "behaviors": p.behaviors or [],
        "preferences": p.preferences or [],
        "motivations": p.motivations or [],
        "objections": p.objections or [],
        "commercial_profile": commercial,
        "technology_profile": p.technology_profile or {},
        "evidence_citations": p.evidence_citations or [],
        "dataset_refs": p.dataset_refs or [],
        "grounding_score": p.grounding_score,
        "confidence": p.confidence,
        "validation_warnings": p.validation_warnings or [],
        "is_synthetic": p.is_synthetic,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }



def _serialize_persona_run(r: PersonaGenerationRuns) -> dict[str, Any]:
    return {
        "id": r.id,
        "study_id": r.study_id,
        "user_id": r.user_id,
        "segmentation_run_id": r.segmentation_run_id,
        "status": r.status,
        "configuration": r.configuration or {},
        "target_count": r.target_count,
        "generated_count": r.generated_count,
        "valid_count": r.valid_count,
        "warning_count": r.warning_count,
        "dataset_versions": r.dataset_versions or [],
        "evidence_snapshot": r.evidence_snapshot or {},
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _verify_study_access(study_id: str, current_user: Optional[Users], session: AsyncSession) -> Studies:
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study '{study_id}' not found.",
        )
    return study


# ---------------------------------------------------------------------------
# Study-Scoped Persona Endpoints (Part 5)
# ---------------------------------------------------------------------------

@router.get("/studies/{study_id}/personas")
async def list_study_personas_endpoint(
    study_id: str,
    segment_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    generation_run_id: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List synthetic customer personas for a study with segment mapping and grounding stats."""
    await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    personas = await service.list_personas(
        study_id=study_id,
        user_id=current_user.id if current_user else None,
        segment_id=segment_id,
        status=status_filter,
        generation_run_id=generation_run_id,
        search=search,
        limit=limit,
        offset=offset,
    )

    # Fetch segment names for mapping
    seg_stmt = select(MarketSegments.id, MarketSegments.name).where(MarketSegments.study_id == study_id)
    seg_results = (await session.execute(seg_stmt)).all()
    seg_map = {sid: sname for sid, sname in seg_results}

    serialized = [_serialize_persona(p, seg_map.get(p.segment_id or "")) for p in personas]

    # Metrics
    avg_score = 0.0
    if serialized:
        avg_score = round(sum(p["grounding_score"] for p in serialized) / len(serialized), 2)

    return {
        "personas": serialized,
        "total": len(serialized),
        "represented_segments": len({p["segment_id"] for p in serialized if p["segment_id"]}),
        "average_grounding_score": avg_score,
    }


@router.post("/studies/{study_id}/personas/generate", status_code=status.HTTP_201_CREATED)
async def generate_study_personas_endpoint(
    study_id: str,
    body: StudyGeneratePersonasRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate grounded synthetic personas for a study across its market segments."""
    await _verify_study_access(study_id, current_user, session)

    llm_service = getattr(request.app.state, "llm_service", None)
    service = PersonaGenerationService(session, llm_service=llm_service)

    try:
        run, personas = await service.create_generation_run(
            study_id=study_id,
            user_id=current_user.id,
            segmentation_run_id=body.segmentation_run_id,
            personas_per_segment=body.personas_per_segment,
            target_count=body.target_count,
            distribution_strategy=body.distribution_strategy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persona generation failed: {exc}",
        ) from exc

    # Segment map
    seg_stmt = select(MarketSegments.id, MarketSegments.name).where(MarketSegments.study_id == study_id)
    seg_results = (await session.execute(seg_stmt)).all()
    seg_map = {sid: sname for sid, sname in seg_results}

    return {
        "run": _serialize_persona_run(run),
        "personas": [_serialize_persona(p, seg_map.get(p.segment_id or "")) for p in personas],
    }


@router.get("/studies/{study_id}/personas/{persona_id}")
async def get_study_persona_endpoint(
    study_id: str,
    persona_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a detailed synthetic persona profile with citations and dataset links."""
    await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    persona = await service.get_persona(
        study_id=study_id,
        persona_id=persona_id,
        user_id=current_user.id if current_user else None,
    )
    if not persona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found.")

    segment_name = None
    if persona.segment_id:
        seg = await session.get(MarketSegments, persona.segment_id)
        if seg:
            segment_name = seg.name

    return _serialize_persona(persona, segment_name)


@router.post("/studies/{study_id}/personas/{persona_id}/regenerate")
async def regenerate_study_persona_endpoint(
    study_id: str,
    persona_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Regenerate a single persona to create a new version while preserving grounding."""
    await _verify_study_access(study_id, current_user, session)

    llm_service = getattr(request.app.state, "llm_service", None)
    service = PersonaGenerationService(session, llm_service=llm_service)

    try:
        persona = await service.regenerate_persona(
            study_id=study_id,
            persona_id=persona_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    segment_name = None
    if persona.segment_id:
        seg = await session.get(MarketSegments, persona.segment_id)
        if seg:
            segment_name = seg.name

    return _serialize_persona(persona, segment_name)


@router.get("/studies/{study_id}/persona-runs")
async def list_study_persona_runs_endpoint(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List historical persona generation runs for a study."""
    await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    runs = await service.list_runs(study_id=study_id, user_id=current_user.id if current_user else None)
    return {"runs": [_serialize_persona_run(r) for r in runs]}


@router.get("/studies/{study_id}/persona-runs/{run_id}")
async def get_study_persona_run_endpoint(
    study_id: str,
    run_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get audit details and progress of a persona generation run."""
    await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    run = await service.get_run(study_id=study_id, run_id=run_id, user_id=current_user.id if current_user else None)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona generation run not found.")
    return _serialize_persona_run(run)


@router.delete("/studies/{study_id}/persona-runs/{run_id}")
async def delete_study_persona_run_endpoint(
    study_id: str,
    run_id: str,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a persona generation run and its generated personas."""
    await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    success = await service.delete_run(study_id=study_id, run_id=run_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona generation run not found.")
    return {"success": True, "message": "Persona generation run and associated personas deleted."}


# ---------------------------------------------------------------------------
# Legacy Endpoints (Preserved for compatibility)
# ---------------------------------------------------------------------------

@router.post("/businesses", status_code=201)
async def create_business_endpoint(
    body: BusinessCreate,
    request: Request,
    current_user: Users = Depends(get_current_user),
) -> dict:
    # M5: industry/target_market are real columns — the description is user
    # content and is never used as a metadata carrier.
    owner_id = current_user.id
    async with request.app.state.db_sessionmaker() as session:
        business = await create_business(
            session,
            body.name,
            body.description or "",
            industry=body.industry,
            target_market=body.target_market,
            owner_id=owner_id,
        )
    return {
        "id": business.id,
        "name": business.name,
        "description": business.description,
        "industry": business.industry,
        "target_market": business.target_market,
        "persona_count": 0,
        "created_at": business.created_at.isoformat() if business.created_at else None,
    }


@router.get("/businesses")
async def list_businesses_endpoint(
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> list[dict]:
    owner_id = current_user.id if current_user else None
    async with request.app.state.db_sessionmaker() as session:
        businesses = await list_businesses(session, owner_id=owner_id)
        count_stmt = select(Personas.business_id, func.count(Personas.id))
        if owner_id:
            count_stmt = count_stmt.where((Personas.owner_id == owner_id) | (Personas.owner_id == "usr_system_holder"))
        counts_res = await session.execute(count_stmt.group_by(Personas.business_id))
        counts_map = dict(counts_res.all())

    results = []
    for b in businesses:
        results.append(
            {
                "id": b.id,
                "name": b.name,
                "description": b.description or "",
                # M5: stored values or null — never invented defaults
                "industry": b.industry,
                "target_market": b.target_market,
                "persona_count": counts_map.get(b.id, 0),
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
        )
    return results


@router.get("/personas")
async def list_personas_legacy_endpoint(
    request: Request,
    business_id: Optional[str] = Query(default=None),
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> list[dict]:
    owner_id = current_user.id if current_user else None
    async with request.app.state.db_sessionmaker() as session:
        personas = await list_personas(session, business_id=business_id, owner_id=owner_id)
    return [p.model_dump(mode="json") for p in personas]


@router.post("/businesses/{business_id}/personas", status_code=201)
async def generate_persona_endpoint(
    business_id: str,
    body: PersonaGenerateRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
) -> dict:
    owner_id = current_user.id
    async with request.app.state.db_sessionmaker() as session:
        business = await get_business(session, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="business not found")
        if business.owner_id not in (current_user.id, "usr_system_holder"):
            raise HTTPException(status_code=404, detail="business not found")

    engine = request.app.state.persona_engine

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
        await save_persona(session, profile, owner_id=owner_id)

    memory_service = getattr(request.app.state, "memory_service", None)
    if memory_service:
        try:
            await memory_service.remember(
                persona_id=profile.id,
                text=f"Identity: {profile.name}, {profile.age}yo {profile.occupation} based in {profile.location}. {profile.description}",
                kind="semantic",
                importance=0.95,
            )
        except Exception:
            # best-effort enrichment — but never silent (M8)
            logger.warning("identity memory write failed for persona %s", profile.id, exc_info=True)

    return profile.model_dump(mode="json")


@router.get("/personas/{persona_id}")
async def get_persona_endpoint(
    persona_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        # Check if legacy store profile exists
        profile = await load_persona(session, persona_id)
        if profile is not None:
            p_row = await session.get(Personas, persona_id)
            if current_user and p_row and p_row.owner_id not in (current_user.id, "usr_system_holder"):
                raise HTTPException(status_code=404, detail="persona not found")
            return profile.model_dump(mode="json")
        # Otherwise fallback to study-scoped persona row
        p_row = await session.get(Personas, persona_id)
        if p_row is not None:
            if current_user and p_row.owner_id not in (current_user.id, "usr_system_holder"):
                raise HTTPException(status_code=404, detail="persona not found")
            return _serialize_persona(p_row)
    raise HTTPException(status_code=404, detail="persona not found")



@router.get("/personas/{persona_id}/memories")
async def get_persona_memories_endpoint(
    persona_id: str,
    request: Request,
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    # M9: a missing service and a missing persona must be distinguishable from
    # "persona exists and has no memories yet" — never a blanket `200 []`.
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail="memory service not configured")

    async with request.app.state.db_sessionmaker() as session:
        # save_persona always writes a Personas row, so one PK lookup covers
        # both the legacy profile store and study-scoped personas.
        if await session.get(Personas, persona_id) is None:
            raise HTTPException(status_code=404, detail="persona not found")

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
