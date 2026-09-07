"""FastAPI router for Market Segmentation & Segment Builder."""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.deps import get_session, require_study_access
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import (
    DatasetSources,
    EvidenceClaims,
    MarketSegments,
    SegmentationRuns,
    Studies,
)
from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.service import SegmentationEngineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studies", tags=["segmentation"])


class RunSegmentationRequest(BaseModel):
    desired_clusters: Optional[int] = Field(None, ge=2, le=6)
    configuration: Optional[dict[str, Any]] = None


class CompareSegmentsRequest(BaseModel):
    segment_ids: list[str] = Field(..., min_length=2, max_length=6)


def _serialize_run(r: SegmentationRuns) -> dict[str, Any]:
    return {
        "id": r.id,
        "study_id": r.study_id,
        "user_id": r.user_id,
        "status": r.status,
        "method": r.method,
        "configuration": r.configuration or {},
        "dataset_versions": r.dataset_versions or [],
        "evidence_snapshot": r.evidence_snapshot or {},
        "segment_count": r.segment_count,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_segment(s: MarketSegments) -> dict[str, Any]:
    return {
        "id": s.id,
        "study_id": s.study_id,
        "user_id": s.user_id,
        "segmentation_run_id": s.segmentation_run_id,
        "name": s.name,
        "cluster_label": s.cluster_label,
        "description": s.description,
        "population_count": s.population_count,
        "population_percentage": s.population_percentage,
        "confidence_score": s.confidence_score,
        "status": s.status,
        "characteristics": s.characteristics or {},
        "variable_distributions": s.variable_distributions or {},
        "evidence_citations": s.evidence_citations or [],
        "differentiation_summary": s.differentiation_summary,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


async def _verify_study_access(
    session: AsyncSession, study_id: str, current_user: Optional[Users], *, write: bool = False
) -> Studies:
    """Verify study exists and caller has access. Return 404 for unowned studies.

    Delegates to the canonical `user_owns_study` rule — anonymous callers
    only pass for demo / anonymous-tenant studies (never any owned study).
    ``write=True`` selects the strict write predicate instead, so the demo's
    read allowance never grants mutations (readable but not writable is an
    honest 403, never a false 404).
    """
    study_res = await session.execute(select(Studies).where(Studies.id == study_id))
    study = study_res.scalars().first()
    return require_study_access(
        study, current_user, write=write, not_found_detail=f"Study '{study_id}' not found."
    )


@router.get("/{study_id}/segmentation/readiness")
async def get_segmentation_readiness(
    study_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Check whether a study is ready for market segmentation."""
    study = await _verify_study_access(session, study_id, current_user)
    user_id = current_user.id if current_user else None

    # Fetch datasets
    ds_query = select(DatasetSources).where(DatasetSources.study_id == study_id)
    if user_id:
        ds_query = ds_query.where(DatasetSources.user_id == user_id)
    ds_res = await session.execute(ds_query)
    datasets = list(ds_res.scalars().all())

    # If no study-specific datasets, check user ready datasets
    if not datasets and user_id:
        user_ds_res = await session.execute(
            select(DatasetSources).where(DatasetSources.user_id == user_id, DatasetSources.status.in_(("ready", "processed")))
        )
        datasets = list(user_ds_res.scalars().all())

    # Fetch claims
    claims_query = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
    if user_id:
        claims_query = claims_query.where(EvidenceClaims.user_id == user_id)
    claims_res = await session.execute(claims_query)
    claims = list(claims_res.scalars().all())

    study_ctx = {
        "title": study.title,
        "prompt": study.prompt or study.title,
        "target_audience": study.target_audience or "",
        "pricing_hypothesis": study.pricing_hypothesis or "",
    }
    return check_segmentation_readiness(study_id, datasets, claims, study_ctx)


@router.post("/{study_id}/segmentation", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def run_segmentation(
    study_id: str,
    request: Request,
    request_data: Optional[RunSegmentationRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Trigger a new market segmentation run for a study."""
    study = await _verify_study_access(session, study_id, current_user, write=True)
    user_id = current_user.id if current_user else study.user_id

    llm_service = getattr(request.app.state, "llm_service", None)
    service = SegmentationEngineService(session=session, llm_service=llm_service)

    desired_clusters = request_data.desired_clusters if request_data else None
    config = request_data.configuration if request_data else None

    try:
        run, segments = await service.run_segmentation(
            study_id=study_id,
            user_id=user_id,
            desired_clusters=desired_clusters,
            configuration=config,
        )
        return {
            "run": _serialize_run(run),
            "segments": [_serialize_segment(s) for s in segments],
        }
    except ValueError as val_err:
        # Deliberate, user-facing validation messages stay verbatim.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except Exception:
        logger.error("segmentation run failed for study %s", study_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Segmentation failed. Please try again.",
        )


@router.get("/{study_id}/segmentation/runs")
async def list_segmentation_runs(
    study_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """List historical segmentation runs for a study."""
    await _verify_study_access(session, study_id, current_user)
    user_id = current_user.id if current_user else None

    query = select(SegmentationRuns).where(SegmentationRuns.study_id == study_id).order_by(SegmentationRuns.created_at.desc())
    if user_id:
        query = query.where(SegmentationRuns.user_id == user_id)

    res = await session.execute(query)
    runs = list(res.scalars().all())
    return [_serialize_run(r) for r in runs]


@router.get("/{study_id}/segmentation/runs/{run_id}")
async def get_segmentation_run(
    study_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Get a specific segmentation run with dataset versions and progress."""
    await _verify_study_access(session, study_id, current_user)
    user_id = current_user.id if current_user else None

    query = select(SegmentationRuns).where(SegmentationRuns.study_id == study_id, SegmentationRuns.id == run_id)
    if user_id:
        query = query.where(SegmentationRuns.user_id == user_id)

    res = await session.execute(query)
    run = res.scalars().first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmentation run not found.")
    return _serialize_run(run)


@router.get("/{study_id}/segments")
async def list_study_segments(
    study_id: str,
    run_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """List customer segments for a study (defaults to latest completed run if run_id not specified)."""
    await _verify_study_access(session, study_id, current_user)
    user_id = current_user.id if current_user else None

    target_run_id = run_id
    if not target_run_id:
        # Find latest completed run
        run_q = (
            select(SegmentationRuns)
            .where(SegmentationRuns.study_id == study_id, SegmentationRuns.status == "completed")
            .order_by(SegmentationRuns.completed_at.desc())
        )
        if user_id:
            run_q = run_q.where(SegmentationRuns.user_id == user_id)
        latest_run_res = await session.execute(run_q)
        latest_run = latest_run_res.scalars().first()
        if latest_run:
            target_run_id = latest_run.id

    query = select(MarketSegments).where(MarketSegments.study_id == study_id)
    if user_id:
        query = query.where(MarketSegments.user_id == user_id)
    if target_run_id:
        query = query.where(MarketSegments.segmentation_run_id == target_run_id)
    if status_filter:
        query = query.where(MarketSegments.status == status_filter)

    query = query.order_by(MarketSegments.population_percentage.desc())
    res = await session.execute(query)
    segments = list(res.scalars().all())
    return [_serialize_segment(s) for s in segments]


@router.get("/{study_id}/segments/{segment_id}")
async def get_segment_detail(
    study_id: str,
    segment_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Get detailed profile, distributions, and evidence citations for a segment."""
    await _verify_study_access(session, study_id, current_user)
    user_id = current_user.id if current_user else None

    query = select(MarketSegments).where(MarketSegments.study_id == study_id, MarketSegments.id == segment_id)
    if user_id:
        query = query.where(MarketSegments.user_id == user_id)

    res = await session.execute(query)
    seg = res.scalars().first()
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found.")
    return _serialize_segment(seg)


@router.post("/{study_id}/segments/compare")
async def compare_segments(
    study_id: str,
    payload: CompareSegmentsRequest,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Generate side-by-side comparison for 2 to 4 segments."""
    await _verify_study_access(session, study_id, current_user, write=True)
    user_id = current_user.id if current_user else None

    service = SegmentationEngineService(session=session)
    try:
        return await service.get_segment_comparison(study_id, user_id, payload.segment_ids)
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@router.delete("/{study_id}/segmentation/runs/{run_id}")
async def delete_segmentation_run(
    study_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Delete a segmentation run and its associated segments."""
    await _verify_study_access(session, study_id, current_user, write=True)
    user_id = current_user.id if current_user else None

    run_q = select(SegmentationRuns).where(SegmentationRuns.study_id == study_id, SegmentationRuns.id == run_id)
    if user_id:
        run_q = run_q.where(SegmentationRuns.user_id == user_id)
    run_res = await session.execute(run_q)
    run = run_res.scalars().first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segmentation run not found.")

    # Delete segments
    seg_q = select(MarketSegments).where(MarketSegments.segmentation_run_id == run_id)
    seg_res = await session.execute(seg_q)
    for seg in seg_res.scalars().all():
        await session.delete(seg)

    await session.delete(run)
    await session.commit()
    return {"status": "deleted", "id": run_id}
