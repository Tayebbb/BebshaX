"""FastAPI router for study research runs, evidence sources, chunks, claims, research plans, and discovered dataset candidates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.deps import get_session, require_study_access, user_owns_study
from bebshax.api.errors import APIError
from bebshax.api.jobs import cancel_job_async, get_job_async, start_job_async
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import (
    EvidenceChunks,
    EvidenceClaims,
    EvidenceSources,
    ResearchRuns,
    Studies,
)
from bebshax.research.service import ResearchEngineService
from bebshax.research.vector_search import VectorSearchEngine
from bebshax.jobs.runtime import JobContext

router = APIRouter(prefix="/studies", tags=["evidence"])

# Semantic retrieval breadth: 6 chunks ≈ one screen of ranked evidence; the
# ceiling keeps a single request from scanning/serializing whole corpora.
DEFAULT_SEMANTIC_TOP_K = 6
MAX_SEMANTIC_TOP_K = 50


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=DEFAULT_SEMANTIC_TOP_K, ge=1, le=MAX_SEMANTIC_TOP_K)


def _serialize_run(r: ResearchRuns) -> dict[str, Any]:
    return {
        "id": r.id,
        "job_id": ((r.step_progress or {}).get("summary") or {}).get("job_id"),
        "study_id": r.study_id,
        "user_id": r.user_id,
        "status": r.status,
        "current_step": r.current_step,
        "query_count": r.query_count,
        "source_count": r.source_count,
        "claim_count": r.claim_count,
        "dataset_candidate_count": r.dataset_candidate_count,
        "dataset_imported_count": r.dataset_imported_count,
        "step_progress": r.step_progress or {},
        # Provenance markers written by the run: plan/queries source, evidence
        # provider, no_live_evidence, claims_status, served_by, error_code.
        "summary": (r.step_progress or {}).get("summary") or {},
        "research_plan": r.research_plan,
        "queries": r.queries or [],
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_source(s: EvidenceSources, claims_count: int = 0) -> dict[str, Any]:
    return {
        "id": s.id,
        "study_id": s.study_id,
        "user_id": s.user_id,
        "run_id": s.run_id,
        "source_type": s.source_type,
        "title": s.title,
        "url": s.url,
        "publisher": s.publisher or "Web Source",
        "content": s.content,
        "content_hash": s.content_hash,
        "relevance_score": s.relevance_score,
        "status": s.status,
        "claims_count": claims_count,
        "metadata_payload": s.metadata_payload or {},
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_claim(c: EvidenceClaims) -> dict[str, Any]:
    return {
        "id": c.id,
        "study_id": c.study_id,
        "user_id": c.user_id,
        "run_id": c.run_id,
        "claim_text": c.claim_text,
        "status": c.status,
        "category": c.category,
        "confidence": c.confidence,
        "supporting_source_ids": c.supporting_source_ids or [],
        "supporting_chunk_ids": c.supporting_chunk_ids or [],
        "contradicting_source_ids": c.contradicting_source_ids or [],
        "rationale": c.rationale,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


@router.post("/{study_id}/research", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/minute")
async def start_study_research(
    study_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=200),
) -> dict[str, Any]:
    """Trigger a new autonomous evidence and dataset research run for a study."""
    study = await session.get(Studies, study_id)
    # Write gate: this run persists evidence rows and spends LLM budget, so the
    # `is_demo` read allowance must not apply (readable-but-not-writable -> 403).
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    llm_service = getattr(request.app.state, "llm_service", None)
    # Deployments/tests may pin the evidence provider (e.g. an offline sample
    # corpus); the default is the live keyless Wikipedia provider.
    search_provider = getattr(request.app.state, "research_search_provider", None)
    service = getattr(request.app.state, "research_engine", None)
    if service is None:
        service = ResearchEngineService(llm_service=llm_service, search_provider=search_provider)
        request.app.state.research_engine = service
        register = getattr(request.app.state, "register_runtime_resource", None)
        if callable(register) and callable(getattr(service, "aclose", None)):
            register(service)
    owner_id = current_user.id
    study_input = {name: getattr(study, name) for name in (
        "id", "user_id", "title", "prompt", "target_audience", "pricing_hypothesis", "revision",
    )}
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    maker = request.app.state.db_sessionmaker
    await session.rollback()

    async def prepare(db_session: AsyncSession, job: dict[str, Any]) -> dict[str, Any]:
        current = await db_session.scalar(select(Studies).where(
            Studies.id == study_id, Studies.user_id == owner_id,
        ).with_for_update())
        if current is None:
            raise APIError(404, "Study not found.", error_code="not_found")
        if any(getattr(current, name) != value for name, value in study_input.items()):
            raise APIError(409, "The study changed before research admission.", error_code="research_input_changed")
        db_session.add(ResearchRuns(
            id=run_id, study_id=study_id, user_id=owner_id, status="queued", current_step="queued",
            step_progress={"summary": {"job_id": job["job_id"]}},
        ))
        return {"run_id": run_id}

    async def runner(job: JobContext) -> None:
        async with maker() as work_session:
            run = await service.run_study_research(
                work_session, Studies(**study_input), user_id=owner_id,
                job=job, run_id=job["result_refs"]["run_id"],
            )
            job["result"] = _serialize_run(run)

    job = await start_job_async(
        request.app, kind="research_generation", scope_id=study_id, user_id=owner_id,
        input_data={"study": study_input}, idempotency_key=idempotency_key, prepare=prepare, runner=runner,
    )
    run = await session.get(ResearchRuns, job["result_refs"]["run_id"])
    if run is None:
        raise APIError(404, "Research run is no longer available.", error_code="not_found")
    return _serialize_run(run)


async def _reconcile_research_job(app: Any, job: dict[str, Any]) -> None:
    if job["state"] not in {"failed", "cancelled", "interrupted", "timed_out"}:
        return
    run_id = (job.get("result_refs") or {}).get("run_id")
    if not run_id:
        return
    async with app.state.db_sessionmaker() as session, session.begin():
        await session.execute(update(ResearchRuns).where(
            ResearchRuns.id == run_id, ResearchRuns.study_id == job["scope_id"], ResearchRuns.user_id == job["user_id"],
            ResearchRuns.status.notin_(("completed", "failed", "cancelled", "interrupted", "timed_out")),
        ).values(status=job["state"], current_step=job["state"], error_message=job["error"], completed_at=datetime.now(timezone.utc)))


@router.get("/{study_id}/research/jobs/{job_id}")
async def get_research_job(study_id: str, job_id: str, request: Request, current_user: Users = Depends(get_current_user)) -> dict[str, Any]:
    job = await get_job_async(request.app, job_id, kind="research_generation", scope_id=study_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Research job not found.", error_code="not_found")
    await _reconcile_research_job(request.app, job)
    return job


@router.post("/{study_id}/research/jobs/{job_id}/cancel")
async def cancel_research_job(study_id: str, job_id: str, request: Request, current_user: Users = Depends(get_current_user)) -> dict[str, Any]:
    job = await cancel_job_async(request.app, job_id, kind="research_generation", scope_id=study_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Research job not found.", error_code="not_found")
    await _reconcile_research_job(request.app, job)
    return job


@router.get("/{study_id}/research")
async def list_study_research_runs(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List research runs executed for a study."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    stmt = select(ResearchRuns).where(ResearchRuns.study_id == study_id).order_by(ResearchRuns.created_at.desc())
    result = await session.execute(stmt)
    runs = list(result.scalars().all())
    return [_serialize_run(r) for r in runs]


@router.get("/{study_id}/research/plan")
async def get_study_research_plan(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the latest structured research plan generated for a study."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    service = ResearchEngineService()
    plan = await service.get_research_plan(session, study_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No research plan found for this study")
    return plan


@router.get("/{study_id}/research/{run_id}")
async def get_study_research_run(
    study_id: str,
    run_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the current progress status and details of a research run."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    run = await session.get(ResearchRuns, run_id)
    if not run or run.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Research run '{run_id}' not found")

    job_id = ((run.step_progress or {}).get("summary") or {}).get("job_id")
    if request is not None and job_id and current_user is not None:
        await session.rollback()
        job = await get_job_async(request.app, job_id, kind="research_generation", scope_id=study_id, user_id=current_user.id)
        if job is not None:
            await _reconcile_research_job(request.app, job)
        run = await session.get(ResearchRuns, run_id, populate_existing=True)
        if run is None:
            raise APIError(404, "Research run not found.", error_code="not_found")
    return _serialize_run(run)


@router.get("/{study_id}/evidence/summary")
async def get_study_evidence_summary(
    study_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get high-level evidence metrics (coverage, supported %, inferred %, unverified %, counts)."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    service = ResearchEngineService()
    return await service.get_evidence_summary(session, study_id)


@router.get("/{study_id}/evidence/sources")
async def list_study_evidence_sources(
    study_id: str,
    source_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List research sources collected for a study with optional type and text filters."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    stmt = select(EvidenceSources).where(EvidenceSources.study_id == study_id)
    if source_type and source_type.lower() != "all":
        stmt = stmt.where(EvidenceSources.source_type == source_type.lower())

    stmt = stmt.order_by(EvidenceSources.relevance_score.desc(), EvidenceSources.created_at.desc())
    result = await session.execute(stmt)
    sources = list(result.scalars().all())

    # Get claims count for each source
    claims_stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
    claims_res = await session.execute(claims_stmt)
    all_claims = list(claims_res.scalars().all())

    source_claims_count: dict[str, int] = {}
    for cl in all_claims:
        for sid in (cl.supporting_source_ids or []):
            source_claims_count[sid] = source_claims_count.get(sid, 0) + 1

    if search and search.strip():
        q = search.strip().lower()
        sources = [s for s in sources if q in s.title.lower() or (s.publisher and q in s.publisher.lower()) or q in s.content.lower()]

    return [_serialize_source(s, source_claims_count.get(s.id, 0)) for s in sources]


@router.get("/{study_id}/evidence/sources/{source_id}")
async def get_study_evidence_source_detail(
    study_id: str,
    source_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full details of a specific source including its chunks."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    source = await session.get(EvidenceSources, source_id)
    if not source or source.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")

    chunks_stmt = select(EvidenceChunks).where(EvidenceChunks.source_id == source_id).order_by(EvidenceChunks.chunk_index.asc())
    chunks_res = await session.execute(chunks_stmt)
    chunks = list(chunks_res.scalars().all())

    data = _serialize_source(source)
    data["chunks"] = [
        {"id": c.id, "chunk_index": c.chunk_index, "content": c.content, "created_at": c.created_at.isoformat()}
        for c in chunks
    ]
    return data


@router.get("/{study_id}/evidence/claims")
async def list_study_evidence_claims(
    study_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List structured empirical claims extracted for a study."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
    if status_filter and status_filter.lower() != "all":
        stmt = stmt.where(EvidenceClaims.status == status_filter.lower())
    if category and category.lower() != "all":
        stmt = stmt.where(EvidenceClaims.category == category.lower())

    stmt = stmt.order_by(EvidenceClaims.confidence.desc(), EvidenceClaims.created_at.desc())
    result = await session.execute(stmt)
    claims = list(result.scalars().all())

    if search and search.strip():
        q = search.strip().lower()
        claims = [c for c in claims if q in c.claim_text.lower() or (c.rationale and q in c.rationale.lower())]

    return [_serialize_claim(c) for c in claims]


@router.get("/{study_id}/evidence/claims/{claim_id}")
async def get_study_evidence_claim_detail(
    study_id: str,
    claim_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full provenance for a claim including supporting sources, excerpts, and similarity scores."""
    study = await session.get(Studies, study_id)
    if not study or not user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    claim = await session.get(EvidenceClaims, claim_id)
    if not claim or claim.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    data = _serialize_claim(claim)

    supporting_sources = []
    if claim.supporting_source_ids:
        src_stmt = select(EvidenceSources).where(EvidenceSources.id.in_(claim.supporting_source_ids))
        src_res = await session.execute(src_stmt)
        sources = list(src_res.scalars().all())
        supporting_sources = [_serialize_source(s) for s in sources]

    supporting_chunks = []
    if claim.supporting_chunk_ids:
        chk_stmt = select(EvidenceChunks).where(EvidenceChunks.id.in_(claim.supporting_chunk_ids))
        chk_res = await session.execute(chk_stmt)
        chunks = list(chk_res.scalars().all())
        supporting_chunks = [
            {"id": c.id, "source_id": c.source_id, "chunk_index": c.chunk_index, "content": c.content}
            for c in chunks
        ]

    contradicting_sources = []
    if claim.contradicting_source_ids:
        csrc_stmt = select(EvidenceSources).where(EvidenceSources.id.in_(claim.contradicting_source_ids))
        csrc_res = await session.execute(csrc_stmt)
        csources = list(csrc_res.scalars().all())
        contradicting_sources = [_serialize_source(s) for s in csources]

    data["supporting_sources"] = supporting_sources
    data["supporting_chunks"] = supporting_chunks
    data["contradicting_sources"] = contradicting_sources
    return data


@router.post("/{study_id}/evidence/search")
async def semantic_search_evidence(
    study_id: str,
    payload: SemanticSearchRequest,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Perform semantic vector retrieval against a study's evidence chunks."""
    study = await session.get(Studies, study_id)
    # Embedding a caller-supplied query costs compute: owner token required
    # (readable-but-not-writable, e.g. the shared demo, gets an honest 403).
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    engine = VectorSearchEngine()
    results = await engine.search_chunks(session, study_id, payload.query, top_k=payload.top_k)

    return [
        {
            "chunk_id": chunk.id,
            "source_id": chunk.source_id,
            "content": chunk.content,
            "similarity_score": score,
            "metadata": chunk.metadata_payload,
        }
        for chunk, score in results
    ]

