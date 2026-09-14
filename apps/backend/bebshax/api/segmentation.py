"""FastAPI router for Market Segmentation & Segment Builder."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.deps import get_session, require_study_access
from bebshax.api.errors import APIError
from bebshax.api.jobs import cancel_job_async, get_job_async, replay_job_input, run_job_inline
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import (
    DatasetSources,
    EvidenceClaims,
    MarketSegments,
    SegmentationRuns,
    Studies,
)
from bebshax.llm.failures import LLMError
from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.service import SegmentationEngineService, capture_segmentation_input_versions
from bebshax.utils.explicit_failures import ExplicitFailure
from bebshax.jobs.orm import DurableJobs
from bebshax.jobs.runtime import FencedSession, JobContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/studies", tags=["segmentation"])


class RunSegmentationRequest(BaseModel):
    desired_clusters: Optional[int] = Field(None, ge=2, le=6)
    configuration: Optional[dict[str, Any]] = None


class CompareSegmentsRequest(BaseModel):
    segment_ids: list[str] = Field(..., min_length=2, max_length=6)


def _serialize_run(r: SegmentationRuns, *, current_inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
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
    if current_inputs is not None:
        # Segments outlive their inputs silently otherwise (live 2026-09-14: the
        # dataset was deleted, three "Data Backed" cards stayed with no warning).
        recorded = (r.configuration or {}).get("input_versions")
        present = {item["id"] for item in current_inputs.get("datasets", [])}
        payload["missing_datasets"] = [
            {"dataset_id": item.get("dataset_id"), "name": item.get("name")}
            for item in (r.dataset_versions or []) if item.get("dataset_id") not in present
        ]
        payload["inputs_changed"] = recorded is not None and recorded != current_inputs
    return payload


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
    current_user: Users = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=200),
):
    """Trigger a new market segmentation run for a study."""
    study = await _verify_study_access(session, study_id, current_user, write=True)
    user_id = current_user.id

    llm_service = getattr(request.app.state, "llm_service", None)

    desired_clusters = request_data.desired_clusters if request_data else None
    config = request_data.configuration if request_data else None
    command = {
        "study_id": study_id, "desired_clusters": desired_clusters, "configuration": config,
        "input_versions": await capture_segmentation_input_versions(session, study_id, user_id),
    }
    command = await replay_job_input(
        request.app, kind="segmentation", scope_id=study_id, user_id=user_id,
        idempotency_key=idempotency_key, input_data=command, snapshot_fields=frozenset({"input_versions"}),
    )
    maker = request.app.state.db_sessionmaker
    await session.rollback()

    async def operation(job: JobContext) -> dict[str, Any]:
        await job.begin_item("segmentation", input_data=command)

        async def checkpoint(db_session: AsyncSession) -> None:
            runs = [row for row in [*db_session.new, *db_session.identity_map.values()]
                    if isinstance(row, SegmentationRuns) and row.study_id == study_id and row.user_id == user_id]
            for run in runs:
                run.configuration = {**(run.configuration or {}), "job_id": job["job_id"]}
                await db_session.flush()
                refs = {"run_id": run.id}
                job["result_refs"] = refs
                await db_session.execute(update(DurableJobs).where(DurableJobs.id == job["job_id"]).values(result_refs=refs))
                if run.status == "completed":
                    await job.complete_item("segmentation", result_refs=refs, session=db_session)

        async with maker() as work_session:
            fenced = FencedSession(work_session, job, before_commit=checkpoint)
            service = SegmentationEngineService(session=cast(AsyncSession, fenced), llm_service=llm_service)
            run, segments = await service.run_segmentation(
                study_id=study_id, user_id=user_id, desired_clusters=desired_clusters, configuration=config,
                expected_input_versions=command["input_versions"],
            )
            return {"run": _serialize_run(run), "segments": [_serialize_segment(segment) for segment in segments]}

    try:
        return await run_job_inline(
            request.app, kind="segmentation", scope_id=study_id, user_id=user_id,
            input_data=command, operation=operation, idempotency_key=idempotency_key,
        )
    except APIError:
        raise
    except ValueError as val_err:
        # Deliberate, user-facing validation messages stay verbatim.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))
    except (ExplicitFailure, LLMError):
        # segmentation_requires_data / llm_unavailable / segment_interpretation_failed /
        # routing failures: the global handlers produce the coded envelope.
        raise
    except Exception:
        logger.error("segmentation run failed for study %s", study_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Segmentation failed. Please try again.",
        )


async def _reconcile_segmentation_job(app: Any, job: dict[str, Any]) -> None:
    if job["state"] not in {"failed", "cancelled", "interrupted", "timed_out"}:
        return
    run_id = (job.get("result_refs") or {}).get("run_id")
    if not run_id:
        return
    async with app.state.db_sessionmaker() as session, session.begin():
        await session.execute(update(SegmentationRuns).where(
            SegmentationRuns.id == run_id, SegmentationRuns.study_id == job["scope_id"], SegmentationRuns.user_id == job["user_id"],
            SegmentationRuns.status.notin_(("completed", "failed", "cancelled", "interrupted", "timed_out")),
        ).values(status=job["state"], error_message=job["error"], completed_at=datetime.now(timezone.utc)))


@router.get("/{study_id}/segmentation/jobs/{job_id}")
async def get_segmentation_job(study_id: str, job_id: str, request: Request, current_user: Users = Depends(get_current_user)) -> dict[str, Any]:
    job = await get_job_async(request.app, job_id, kind="segmentation", scope_id=study_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Segmentation job not found.", error_code="not_found")
    await _reconcile_segmentation_job(request.app, job)
    return job


@router.post("/{study_id}/segmentation/jobs/{job_id}/cancel")
async def cancel_segmentation_job(study_id: str, job_id: str, request: Request, current_user: Users = Depends(get_current_user)) -> dict[str, Any]:
    job = await cancel_job_async(request.app, job_id, kind="segmentation", scope_id=study_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Segmentation job not found.", error_code="not_found")
    await _reconcile_segmentation_job(request.app, job)
    return job


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
    current_inputs = await capture_segmentation_input_versions(session, study_id, user_id) if runs else None
    return [_serialize_run(r, current_inputs=current_inputs) for r in runs]


@router.get("/{study_id}/segmentation/runs/{run_id}")
async def get_segmentation_run(
    study_id: str,
    run_id: str,
    request: Request,
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
    job_id = (run.configuration or {}).get("job_id")
    if job_id and current_user is not None:
        await session.rollback()
        job = await get_job_async(request.app, job_id, kind="segmentation", scope_id=study_id, user_id=current_user.id)
        if job is not None:
            await _reconcile_segmentation_job(request.app, job)
        run = await session.get(SegmentationRuns, run_id, populate_existing=True)
        if run is None:
            raise APIError(404, "Segmentation run not found.", error_code="not_found")
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
