"""Persona REST API: study-scoped synthetic persona generation, retrieval, and legacy compatibility."""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.jobs import get_job, start_job
from bebshax.api.deps import get_session, owner_accessible, require_study_access
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import MarketSegments, PersonaGenerationRuns, Personas, Studies
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
from bebshax.tenancy import allowed_owner_ids

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
        "country_code": getattr(p, "country_code", None) or None,
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


async def _verify_study_access(
    study_id: str, current_user: Optional[Users], session: AsyncSession, *, write: bool = False
) -> Studies:
    """``write=True`` selects the strict write predicate: the ``is_demo`` read
    allowance must never let a non-owner mutate the shared demo (readable but
    not writable is an honest 403, never a false 404)."""
    study = await session.get(Studies, study_id)
    return require_study_access(
        study, current_user, write=write, not_found_detail=f"Study '{study_id}' not found."
    )


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
    study = await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    personas = await service.list_personas(
        study_id=study_id,
        # The demo is public-readable by design and its rows are stamped with
        # the seeded owner's user_id — scoping by the READER's id hid the demo
        # persona from every signed-in non-owner (card said 1, list said 0).
        user_id=None if study.is_demo else (current_user.id if current_user else None),
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
@limiter.limit("20/minute")
async def generate_study_personas_endpoint(
    study_id: str,
    body: StudyGeneratePersonasRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate grounded synthetic personas for a study across its market segments."""
    await _verify_study_access(study_id, current_user, session, write=True)

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
    except (ContextWindowExceeded, AllCandidatesFailed):
        # Rendered by the global handlers (413 / 503 with attempts) — never
        # flattened into a bare 500 by the catch-all below.
        raise
    except Exception as exc:
        logger.error("persona generation failed for study %s", study_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Persona generation failed. Please try again.",
        ) from exc

    # Segment map
    seg_stmt = select(MarketSegments.id, MarketSegments.name).where(MarketSegments.study_id == study_id)
    seg_results = (await session.execute(seg_stmt)).all()
    seg_map = {sid: sname for sid, sname in seg_results}

    return {
        "run": _serialize_persona_run(run),
        "personas": [_serialize_persona(p, seg_map.get(p.segment_id or "")) for p in personas],
    }


# ---------------------------------------------------------------------------
# Async persona-generation jobs: a run generates N personas across segments
# at real free-tier LLM latency (minutes) — beyond any sane HTTP timeout.
# POST starts a background job (202), the UI polls. Personas/run rows are
# persisted by the service as it completes; only job STATUS is in-memory.
# ---------------------------------------------------------------------------

@router.post("/studies/{study_id}/personas/generate/jobs", status_code=202)
@limiter.limit("10/minute")
async def start_persona_generation_job(
    study_id: str,
    body: StudyGeneratePersonasRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start persona generation in the background; poll the job endpoint."""
    await _verify_study_access(study_id, current_user, session, write=True)

    app = request.app
    llm_service = getattr(app.state, "llm_service", None)
    sessionmaker_ = getattr(app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    user_id = current_user.id
    cfg = body  # detach before request scope ends

    async def _runner(job: dict[str, Any]) -> None:
        # The request session is gone by now — the job owns its own session.
        async with sessionmaker_() as job_session:
            service = PersonaGenerationService(job_session, llm_service=llm_service)
            run, personas = await service.create_generation_run(
                study_id=study_id,
                user_id=user_id,
                segmentation_run_id=cfg.segmentation_run_id,
                personas_per_segment=cfg.personas_per_segment,
                target_count=cfg.target_count,
                distribution_strategy=cfg.distribution_strategy,
            )
            seg_stmt = select(MarketSegments.id, MarketSegments.name).where(
                MarketSegments.study_id == study_id
            )
            seg_map = {sid: sname for sid, sname in (await job_session.execute(seg_stmt)).all()}
            job["result"] = {
                "run": _serialize_persona_run(run),
                "personas": [
                    _serialize_persona(p, seg_map.get(p.segment_id or "")) for p in personas
                ],
            }

    job = start_job(
        app,
        kind="persona_generation",
        scope_id=study_id,
        runner=_runner,
        user_id=user_id,
        # Honest domain failures (R2/R6) pass their message through.
        user_safe_exceptions=(PersonaGenerationFailed, ContextWindowExceeded, AllCandidatesFailed),
    )
    return {"job_id": job["job_id"], "study_id": study_id, "status": job["status"]}


@router.get("/studies/{study_id}/personas/generate/jobs/{job_id}")
async def get_persona_generation_job(
    study_id: str,
    job_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Poll a persona-generation job. 404 for unknown/lost jobs (e.g. restart)."""
    await _verify_study_access(study_id, current_user, session)
    job = get_job(request.app, job_id, kind="persona_generation", scope_id=study_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="job not found (it may have been lost in a server restart)",
        )
    return job


@router.get("/studies/{study_id}/personas/{persona_id}")
async def get_study_persona_endpoint(
    study_id: str,
    persona_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a detailed synthetic persona profile with citations and dataset links."""
    study = await _verify_study_access(study_id, current_user, session)
    service = PersonaGenerationService(session)

    persona = await service.get_persona(
        study_id=study_id,
        persona_id=persona_id,
        # Same demo read allowance as the list endpoint above.
        user_id=None if study.is_demo else (current_user.id if current_user else None),
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
@limiter.limit("10/minute")
async def regenerate_study_persona_endpoint(
    study_id: str,
    persona_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Regenerate a single persona to create a new version while preserving grounding."""
    await _verify_study_access(study_id, current_user, session, write=True)

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
    # ContextWindowExceeded / AllCandidatesFailed: global handlers (413 / 503).

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
    await _verify_study_access(study_id, current_user, session, write=True)
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
        # Same owner scope as the listing itself — counts must never leak
        # other tenants' persona volumes on shared businesses.
        count_stmt = (
            select(Personas.business_id, func.count(Personas.id))
            .where(Personas.owner_id.in_(allowed_owner_ids(owner_id)))
            .group_by(Personas.business_id)
        )
        counts_res = await session.execute(count_stmt)
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
@limiter.limit("10/minute")
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
        # Owner gate (strict auth upstream): callers may only generate under
        # their own or shared/system businesses — never another tenant's
        # (B6 stage 3; owner_accessible also covers anon-tenant stamps).
        if not owner_accessible(business.owner_id, current_user):
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
    # ContextWindowExceeded / AllCandidatesFailed: global handlers (413 / 503).

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
            if p_row and not owner_accessible(p_row.owner_id, current_user):
                raise HTTPException(status_code=404, detail="persona not found")
            return profile.model_dump(mode="json")
        # Otherwise fallback to study-scoped persona row
        p_row = await session.get(Personas, persona_id)
        if p_row is not None:
            if not owner_accessible(p_row.owner_id, current_user):
                raise HTTPException(status_code=404, detail="persona not found")
            return _serialize_persona(p_row)
    raise HTTPException(status_code=404, detail="persona not found")



@router.get("/personas/{persona_id}/memories")
async def get_persona_memories_endpoint(
    persona_id: str,
    request: Request,
    kind: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    include_interviewer: bool = Query(
        default=False, description="Also list researcher questions (source=interviewer)"
    ),
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> list[dict]:
    # M9: a missing service and a missing persona must be distinguishable from
    # "persona exists and has no memories yet" — never a blanket `200 []`.
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail="memory service not configured")

    async with request.app.state.db_sessionmaker() as session:
        # save_persona always writes a Personas row, so one PK lookup covers
        # both the legacy profile store and study-scoped personas.
        p_row = await session.get(Personas, persona_id)
        if p_row is None:
            raise HTTPException(status_code=404, detail="persona not found")
        # Memories are persona-private — same owner gate as the persona itself.
        if not owner_accessible(p_row.owner_id, current_user):
            raise HTTPException(status_code=404, detail="persona not found")

    memories = await memory_service.list_for_persona(
        persona_id,
        kind=kind,
        limit=limit,
        sources=None if include_interviewer else ("persona",),
    )
    return [
        {
            "id": m.id,
            "persona_id": m.persona_id,
            "kind": m.kind,
            "text": m.text,
            "importance": m.importance,
            # Who authored the text: the persona's own statements are recollections;
            # interviewer questions are context and are only listed on request.
            "source": m.source,
            "conversation_id": m.conversation_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memories
    ]
