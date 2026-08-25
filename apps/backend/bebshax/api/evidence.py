"""FastAPI router for study research runs, evidence sources, chunks, claims, research plans, and discovered dataset candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.studies import _user_owns_study, get_session
from bebshax.auth.models import Users
from bebshax.db.models import (
    DatasetCandidates,
    DatasetSources,
    EvidenceChunks,
    EvidenceClaims,
    EvidenceSources,
    ResearchPlans,
    ResearchRuns,
    Studies,
)
from bebshax.research.service import ResearchEngineService
from bebshax.research.vector_search import VectorSearchEngine

router = APIRouter(prefix="/studies", tags=["evidence"])


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = 6


def _serialize_run(r: ResearchRuns) -> dict[str, Any]:
    return {
        "id": r.id,
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


@router.post("/{study_id}/research", status_code=status.HTTP_201_CREATED)
async def start_study_research(
    study_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger a new autonomous evidence and dataset research run for a study."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    llm_service = getattr(request.app.state, "llm_service", None)
    service = ResearchEngineService(llm_service=llm_service)
    effective_user_id = current_user.id if current_user else study.user_id

    run = await service.run_study_research(session, study, user_id=effective_user_id)
    return _serialize_run(run)


@router.get("/{study_id}/research")
async def list_study_research_runs(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List research runs executed for a study."""
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
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
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the current progress status and details of a research run."""
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    run = await session.get(ResearchRuns, run_id)
    if not run or run.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Research run '{run_id}' not found")

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
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
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
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

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


# ============================================================================
# Discovered Dataset Candidates Endpoints
# ============================================================================

@router.get("/{study_id}/datasets/candidates")
async def list_study_dataset_candidates(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List public dataset candidates discovered for a study."""
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    service = ResearchEngineService()
    return await service.list_dataset_candidates(session, study_id)


@router.post("/{study_id}/datasets/candidates/{candidate_id}/import")
async def import_study_dataset_candidate(
    study_id: str,
    candidate_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Manually import a discovered dataset candidate into the study's dataset sources."""
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    service = ResearchEngineService()
    effective_user_id = current_user.id if current_user else study.user_id
    try:
        imported_ds = await service.import_candidate_dataset(session, study_id, candidate_id, effective_user_id)
        return {
            "success": True,
            "imported_dataset_id": imported_ds.id,
            "dataset_name": imported_ds.name,
            "row_count": imported_ds.row_count,
            "column_count": imported_ds.column_count,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{study_id}/datasets/candidates/{candidate_id}/reject")
async def reject_study_dataset_candidate(
    study_id: str,
    candidate_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Reject a discovered dataset candidate so it is excluded from auto-selection."""
    study = await session.get(Studies, study_id)
    if not study or not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")

    service = ResearchEngineService()
    try:
        await service.reject_candidate_dataset(session, study_id, candidate_id)
        return {"success": True, "candidate_id": candidate_id, "status": "rejected_by_user"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
