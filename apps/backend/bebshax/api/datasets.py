"""FastAPI endpoints for Dataset Sources, deterministic profiling, study-scoped datasets, and evidence-grounded persona generation."""

from __future__ import annotations

import logging
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.deps import require_study_access
from bebshax.api.errors import APIError
from bebshax.api.limiter import limiter
from bebshax.api.jobs import cancel_job_async, get_job_async, replay_job_input, run_job_inline
from bebshax.auth.models import Users
from bebshax.datasets.orm import DatasetVersions
from bebshax.datasets.parser import DatasetParseError
from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES, DatasetSecurityError
from bebshax.datasets.service import DatasetService, dataset_refresh_input
from bebshax.db.models import DatasetSources, Studies
from bebshax.personas.ml_adapter import get_persona_ml
from bebshax.research.service import ResearchEngineService
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.jobs.runtime import JobContext

logger = logging.getLogger(__name__)

router = APIRouter(tags=["datasets"])


_UPLOAD_CHUNK_BYTES = 64 * 1024


def _oversized_upload() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"Uploaded file exceeds the {MAX_DATASET_FILE_SIZE_BYTES // (1024 * 1024)} MB limit.",
    )


async def _read_upload_or_413(file: UploadFile, request: Optional[Request] = None) -> bytes:
    """Read an upload under the same size ceiling the URL-fetch path enforces.

    The declared Content-Length is rejected up front and the body is then read
    in bounded chunks, so an oversized multipart never becomes fully resident.
    """
    if request is not None:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_DATASET_FILE_SIZE_BYTES:
            raise _oversized_upload()

    size = 0
    chunks: list[bytes] = []
    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
        size += len(chunk)
        if size > MAX_DATASET_FILE_SIZE_BYTES:
            raise _oversized_upload()
        chunks.append(chunk)

    if not size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    return b"".join(chunks)


def _get_dataset_service(request: Request) -> DatasetService:
    sessionmaker_: Optional[sessionmaker[AsyncSession]] = getattr(request.app.state, "db_sessionmaker", None)
    existing = getattr(request.app.state, "dataset_service", None)
    # A cached service bound to a replaced sessionmaker would fence job leases
    # against the wrong database; rebuild it whenever the app's factory changes.
    if isinstance(existing, DatasetService) and (sessionmaker_ is None or existing.sessionmaker is sessionmaker_):
        return existing
    if sessionmaker_ is None:
        raise APIError(503, "Dataset storage is not configured.", error_code="job_store_unavailable")
    llm = getattr(request.app.state, "llm_router", None)
    service = DatasetService(sessionmaker_, llm=llm, ml_generator=get_persona_ml(request.app))
    request.app.state.dataset_service = service
    return service


async def _get_session(request: Request) -> AsyncSession:
    sessionmaker_: Optional[sessionmaker[AsyncSession]] = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker_:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker_() as session:
        yield session


class IngestUrlRequest(BaseModel):
    url: str = Field(max_length=2048)
    name: str = Field(min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=8000)
    study_id: Optional[str] = Field(default=None, max_length=64)
    file_type: Optional[str] = Field(default=None, max_length=16)


class QueryDatasetRequest(BaseModel):
    filter_col: Optional[str] = Field(default=None, max_length=256)
    filter_val: Optional[Any] = None
    limit: int = Field(default=100, ge=1, le=1000)


class GeneratePersonasRequest(BaseModel):
    # Each persona is a sequential LLM call; an unbounded count was unbounded spend.
    requested_count: int = Field(default=10, ge=1, le=50)
    study_id: Optional[str] = Field(default=None, max_length=64)
    business_name: str = Field(default="BebshaX Research Initiative", max_length=256)
    business_description: str = Field(
        default="Evidence-grounded user interview validation", max_length=8000
    )


def _serialize_dataset(ds: DatasetSources) -> dict[str, Any]:
    return {
        "id": ds.id,
        "user_id": ds.user_id,
        "study_id": ds.study_id,
        "name": ds.name,
        "source_type": ds.source_type,
        "source_url": ds.source_url,
        "original_file_name": ds.original_file_name,
        "file_type": ds.file_type,
        "description": ds.description,
        "status": ds.status,
        "row_count": ds.row_count,
        "column_count": ds.column_count,
        "schema_metadata": ds.schema_metadata,
        "statistics": ds.statistics,
        "segments": ds.segments,
        "content_hash": ds.content_hash,
        "is_sample": bool((ds.schema_metadata or {}).get("is_sample", False)),
        "persona_count_generated": ds.persona_count_generated,
        "processing_error": ds.processing_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        "last_processed_at": ds.last_processed_at.isoformat() if ds.last_processed_at else None,
    }


async def _dataset_command(
    request: Request, *, kind: str, scope_id: str, user_id: str, input_data: dict[str, Any],
    operation: Callable[[JobContext], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    async def execute(job: JobContext) -> dict[str, Any]:
        await job.begin_item("dataset", input_data=input_data)
        try:
            return await operation(job)
        except DatasetParseError as exc:
            raise APIError(exc.status_code, exc.detail, error_code=exc.error_code) from exc

    return await run_job_inline(
        request.app, kind=kind, scope_id=scope_id, user_id=user_id, input_data=input_data,
        operation=execute, idempotency_key=request.headers.get("Idempotency-Key"),
    )


async def _refresh_command(request: Request, service: DatasetService, dataset_id: str, user_id: str) -> dict[str, Any]:
    dataset = await service.get_dataset(dataset_id, user_id=user_id)
    if dataset is None or dataset.source_type != "url" or not dataset.source_url:
        raise APIError(404, "Dataset cannot be refreshed (not a URL source or not found).", error_code="not_found")
    async with service.sessionmaker() as session:
        version_id = await session.scalar(select(DatasetVersions.id).where(
            DatasetVersions.dataset_id == dataset.id, DatasetVersions.owner_id == dataset.user_id,
            DatasetVersions.file_path == dataset.file_path, DatasetVersions.content_hash == dataset.content_hash,
        ).order_by(DatasetVersions.version.desc()).limit(1))
    input_data = dataset_refresh_input(dataset, version_id)
    input_data = await replay_job_input(
        request.app, kind="dataset_refresh", scope_id=dataset_id, user_id=user_id,
        idempotency_key=request.headers.get("Idempotency-Key"), input_data=input_data,
        snapshot_fields=frozenset(input_data).difference({"dataset_id"}),
    )

    async def operation(job: JobContext) -> dict[str, Any]:
        dataset, changed = await service.refresh_dataset(dataset_id, user_id=user_id, job=job, expected_input=input_data)
        if dataset is None:
            raise APIError(404, "Dataset cannot be refreshed (not a URL source or not found).", error_code="not_found")
        return {**_serialize_dataset(dataset), "content_changed": changed}

    return await _dataset_command(
        request, kind="dataset_refresh", scope_id=dataset_id, user_id=user_id,
        input_data=input_data, operation=operation,
    )


@router.get("/datasets/jobs/{job_id}")
async def get_dataset_job(
    job_id: str, request: Request, kind: str = Query(..., pattern="^dataset_(upload|url|refresh|personas|import)$"),
    scope_id: str = Query(..., min_length=1, max_length=255), current_user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    job = await get_job_async(request.app, job_id, kind=kind, scope_id=scope_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Dataset job not found.", error_code="not_found")
    return job


@router.post("/datasets/jobs/{job_id}/cancel")
async def cancel_dataset_job(
    job_id: str, request: Request, kind: str = Query(..., pattern="^dataset_(upload|url|refresh|personas|import)$"),
    scope_id: str = Query(..., min_length=1, max_length=255), current_user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    job = await cancel_job_async(request.app, job_id, kind=kind, scope_id=scope_id, user_id=current_user.id)
    if job is None:
        raise APIError(404, "Dataset job not found.", error_code="not_found")
    return job


async def _verify_study_access(
    study_id: str,
    current_user: Optional[Users],
    session: AsyncSession,
    *,
    write: bool = False,
) -> Studies:
    """Canonical study gate (`user_owns_study`) — anonymous callers only
    pass for demo / anonymous-tenant studies, never any owned study.
    ``write=True`` selects the strict write predicate, so the demo's read
    allowance never grants mutations (readable but not writable is an honest
    403, never a false 404)."""
    study = await session.get(Studies, study_id)
    return require_study_access(
        study, current_user, write=write, not_found_detail=f"Study '{study_id}' not found"
    )


async def _verify_study_access_via_service(
    study_id: str,
    current_user: Optional[Users],
    service: DatasetService,
    *,
    write: bool = False,
) -> None:
    """Same gate for the un-nested routes, which take the study id from the
    body/query and have no request-scoped session of their own."""
    async with service.sessionmaker() as session:
        await _verify_study_access(study_id, current_user, session, write=write)


# ============================================================================
# Global User-Scoped Dataset Endpoints
# ============================================================================

@router.get("/datasets", response_model=list[dict[str, Any]])
async def list_datasets(
    study_id: Optional[str] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> list[dict[str, Any]]:
    """List all available datasets scoped to the authenticated user."""
    if study_id:
        await _verify_study_access_via_service(study_id, current_user, service)
    user_id = current_user.id if current_user else None
    datasets = await service.list_datasets(user_id=user_id, study_id=study_id)
    return [_serialize_dataset(ds) for ds in datasets]


@router.post("/datasets/url", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def ingest_dataset_url(
    request: Request,
    payload: IngestUrlRequest,
    current_user: Users = Depends(get_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Fetch external dataset from URL with SSRF validation, parse, profile, and derive segments.

    Authenticated only: an anonymously ingested dataset was stamped with the
    shared anonymous tenant, which is a world-readable pool — so one visitor's
    upload became every other visitor's to read.
    """
    # A study id in the BODY is exactly as sensitive as one in the path: without
    # this gate the route was an unauthenticated cross-tenant write.
    if payload.study_id:
        await _verify_study_access_via_service(payload.study_id, current_user, service, write=True)
    user_id = current_user.id
    async def operation(job: JobContext) -> dict[str, Any]:
        ds = await service.ingest_from_url(
            url=payload.url,
            name=payload.name,
            description=payload.description,
            user_id=user_id,
            study_id=payload.study_id,
            file_type=payload.file_type, job=job,
        )
        return _serialize_dataset(ds)
    try:
        return await _dataset_command(
            request, kind="dataset_url", scope_id=payload.study_id or user_id, user_id=user_id,
            input_data=payload.model_dump(), operation=operation,
        )
    except APIError:
        raise
    except DatasetSecurityError as exc:
        # A blocked URL is the guard doing its job, not a server fault: no
        # traceback (which also printed local paths) — live 2026-09-14.
        logger.info("dataset URL refused for %r: %s", payload.name, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        # Our own validation/SSRF messages are user-facing by design.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("dataset URL ingestion failed for %r", payload.name, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset ingestion failed. Check the URL and file format.",
        ) from exc


@router.post("/datasets/upload", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def upload_dataset_file(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    study_id: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    current_user: Users = Depends(get_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Upload a dataset file (CSV, JSON, TSV, XLSX) to profile and derive segments.

    Authenticated only — see ``ingest_dataset_url`` for why.
    """
    # Same gate as the path-based upload route — a form-supplied study id must
    # not be a way around it.
    if study_id:
        await _verify_study_access_via_service(study_id, current_user, service, write=True)
    content = await _read_upload_or_413(file, request)

    user_id = current_user.id
    filename = file.filename or "dataset.csv"

    async def operation(job: JobContext) -> dict[str, Any]:
        ds = await service.ingest_from_upload(
            content=content,
            original_filename=filename,
            name=name,
            description=description,
            user_id=user_id,
            study_id=study_id,
            file_type=file_type, job=job,
        )
        return _serialize_dataset(ds)
    try:
        return await _dataset_command(
            request, kind="dataset_upload", scope_id=study_id or user_id, user_id=user_id,
            input_data={"sha256": hashlib.sha256(content).hexdigest(), "filename": filename, "name": name,
                        "description": description, "study_id": study_id, "file_type": file_type}, operation=operation,
        )
    except APIError:
        raise
    except ValueError as exc:
        # Our own validation messages are user-facing by design.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("dataset upload processing failed for %r", name, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded dataset could not be processed.",
        ) from exc


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Get full dataset profile, schema metadata, descriptive statistics, and discovered segments."""
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return _serialize_dataset(ds)


@router.get("/datasets/{dataset_id}/preview")
async def get_dataset_preview(
    dataset_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Get paginated row preview of dataset records."""
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return await service.get_dataset_preview(dataset_id=dataset_id, offset=offset, limit=limit, user_id=user_id)


@router.post("/datasets/{dataset_id}/refresh")
# An outbound fetch per call: pinned to the same budget as URL ingestion.
@limiter.limit("10/hour")
async def refresh_dataset(
    dataset_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Re-fetch URL-based dataset and update schema, statistics, and segments."""
    user_id = current_user.id
    try:
        return await _refresh_command(request, service, dataset_id, user_id)
    except (APIError, HTTPException):
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("dataset refresh failed for %s", dataset_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset refresh failed.",
        ) from exc


@router.post("/datasets/{dataset_id}/query")
async def query_dataset(
    dataset_id: str,
    payload: QueryDatasetRequest,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Execute deterministic queries and filters against stored dataset records."""
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return await service.query_dataset(
        dataset_id=dataset_id,
        filter_col=payload.filter_col,
        filter_val=payload.filter_val,
        limit=payload.limit,
    )


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Delete dataset source."""
    user_id = current_user.id if current_user else None
    ok = await service.delete_dataset(dataset_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return {"status": "deleted", "id": dataset_id}


@router.post("/datasets/{dataset_id}/generate-personas")
@limiter.limit("10/minute")
async def generate_personas_from_dataset(
    dataset_id: str,
    payload: GeneratePersonasRequest,
    request: Request,
    current_user: Users = Depends(get_current_user),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Generate synthetic personas strictly grounded in dataset segment distributions and constraints."""
    # Body-supplied study id: personas are persisted against it, so it needs
    # the write gate the path-based routes apply.
    if payload.study_id:
        await _verify_study_access_via_service(payload.study_id, current_user, service, write=True)
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    if ds.study_id is not None and ds.study_id != payload.study_id:
        raise APIError(409, "The dataset belongs to a different study scope.", error_code="dataset_study_mismatch")
    async with service.sessionmaker() as session:
        dataset_version_id = await session.scalar(select(DatasetVersions.id).where(
            DatasetVersions.dataset_id == ds.id, DatasetVersions.owner_id == ds.user_id,
            DatasetVersions.file_path == ds.file_path, DatasetVersions.content_hash == ds.content_hash,
        ).order_by(DatasetVersions.version.desc()).limit(1))
    if dataset_version_id is None:
        raise APIError(
            409, "The dataset has no matching immutable version. Refresh or upload it again.",
            error_code="dataset_version_required",
        )
    async def operation(job: JobContext) -> dict[str, Any]:
        return await service.generate_personas_from_dataset(
            dataset_id=dataset_id,
            requested_count=payload.requested_count,
            user_id=user_id,
            study_id=payload.study_id,
            business_name=payload.business_name,
            business_description=payload.business_description, job=job, expected_dataset_version_id=dataset_version_id,
        )
    try:
        return await _dataset_command(
            request, kind="dataset_personas", scope_id=dataset_id, user_id=current_user.id,
            input_data={"dataset_id": dataset_id, "dataset_version_id": dataset_version_id, **payload.model_dump()},
            operation=operation,
        )
    except APIError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("dataset-grounded persona generation failed for %s", dataset_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Persona generation failed. Please try again.",
        ) from exc


# ============================================================================
# Study-Nested Dataset Endpoints
# ============================================================================

@router.get("/studies/{study_id}/datasets", response_model=list[dict[str, Any]])
async def list_study_datasets(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> list[dict[str, Any]]:
    """List datasets attached to a specific study owned by the caller."""
    await _verify_study_access(study_id, current_user, session)
    user_id = current_user.id if current_user else None
    datasets = await service.list_datasets(user_id=user_id, study_id=study_id)
    return [_serialize_dataset(ds) for ds in datasets]


@router.post("/studies/{study_id}/datasets/url", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def ingest_study_dataset_url(
    study_id: str,
    request: Request,
    payload: IngestUrlRequest,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Ingest external dataset URL directly into a specific study."""
    await _verify_study_access(study_id, current_user, session, write=True)
    user_id = current_user.id
    await session.rollback()
    async def operation(job: JobContext) -> dict[str, Any]:
        ds = await service.ingest_from_url(
            url=payload.url,
            name=payload.name,
            description=payload.description,
            user_id=user_id,
            study_id=study_id,
            file_type=payload.file_type, job=job,
        )
        return _serialize_dataset(ds)
    try:
        return await _dataset_command(
            request, kind="dataset_url", scope_id=study_id, user_id=user_id,
            input_data={**payload.model_dump(), "study_id": study_id}, operation=operation,
        )
    except APIError:
        raise
    except DatasetSecurityError as exc:
        logger.info("dataset URL refused for study %s: %s", study_id, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("study dataset URL ingestion failed for study %s", study_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset ingestion failed. Check the URL and file format.",
        ) from exc


@router.post("/studies/{study_id}/datasets/upload", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def upload_study_dataset_file(
    study_id: str,
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Upload dataset file directly into a specific study."""
    await _verify_study_access(study_id, current_user, session, write=True)
    content = await _read_upload_or_413(file, request)

    user_id = current_user.id
    filename = file.filename or "dataset.csv"
    await session.rollback()
    async def operation(job: JobContext) -> dict[str, Any]:
        ds = await service.ingest_from_upload(
            content=content,
            original_filename=filename,
            name=name,
            description=description,
            user_id=user_id,
            study_id=study_id,
            file_type=file_type, job=job,
        )
        return _serialize_dataset(ds)
    try:
        return await _dataset_command(
            request, kind="dataset_upload", scope_id=study_id, user_id=user_id,
            input_data={"sha256": hashlib.sha256(content).hexdigest(), "filename": filename, "name": name,
                        "description": description, "study_id": study_id, "file_type": file_type}, operation=operation,
        )
    except APIError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("study dataset upload processing failed for study %s", study_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded dataset could not be processed.",
        ) from exc


# ============================================================================
# Discovered Dataset Candidates Endpoints
# ============================================================================

@router.get("/studies/{study_id}/datasets/candidates")
async def list_study_dataset_candidates(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[dict[str, Any]]:
    """List public dataset candidates discovered for a study."""
    await _verify_study_access(study_id, current_user, session)
    service = ResearchEngineService()
    return await service.list_dataset_candidates(session, study_id)


@router.post("/studies/{study_id}/datasets/candidates/{candidate_id}/import")
async def import_study_dataset_candidate(
    study_id: str,
    candidate_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Manually import a discovered dataset candidate into the study's dataset sources."""
    await _verify_study_access(study_id, current_user, session, write=True)
    service = ResearchEngineService()
    effective_user_id = current_user.id
    maker = request.app.state.db_sessionmaker
    await session.rollback()

    async def operation(job: JobContext) -> dict[str, Any]:
        async with maker() as work_session:
            imported_ds = await service.import_candidate_dataset(work_session, study_id, candidate_id, effective_user_id, job=job)
            return {
                "success": True,
                "imported_dataset_id": imported_ds.id,
                "dataset_name": imported_ds.name,
                "row_count": imported_ds.row_count,
                "column_count": imported_ds.column_count,
                "fetched_from": (imported_ds.schema_metadata or {}).get("fetched_from"),
            }
    try:
        return await _dataset_command(
            request, kind="dataset_import", scope_id=study_id, user_id=effective_user_id,
            input_data={"study_id": study_id, "candidate_id": candidate_id}, operation=operation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DatasetParseError as exc:
        # The resource was fetched but is not tabular data we can profile.
        raise APIError(422, f"The downloaded resource could not be parsed as a dataset: {exc}", error_code="dataset_unparseable")


@router.post("/studies/{study_id}/datasets/candidates/{candidate_id}/reject")
async def reject_study_dataset_candidate(
    study_id: str,
    candidate_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    """Reject a discovered dataset candidate so it is excluded from auto-selection."""
    await _verify_study_access(study_id, current_user, session, write=True)
    service = ResearchEngineService()
    try:
        await service.reject_candidate_dataset(session, study_id, candidate_id)
        return {"success": True, "candidate_id": candidate_id, "status": "rejected_by_user"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/studies/{study_id}/datasets/{dataset_id}")
async def get_study_dataset(
    study_id: str,
    dataset_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Get full dataset profile for a study."""
    await _verify_study_access(study_id, current_user, session)
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds or ds.study_id != study_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return _serialize_dataset(ds)


@router.get("/studies/{study_id}/datasets/{dataset_id}/preview")
async def get_study_dataset_preview(
    study_id: str,
    dataset_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Get paginated dataset preview for a study."""
    await _verify_study_access(study_id, current_user, session)
    user_id = current_user.id if current_user else None
    ds = await service.get_dataset(dataset_id, user_id=user_id)
    if not ds or ds.study_id != study_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return await service.get_dataset_preview(dataset_id=dataset_id, offset=offset, limit=limit, user_id=user_id)


@router.post("/studies/{study_id}/datasets/{dataset_id}/refresh")
@limiter.limit("10/hour")
async def refresh_study_dataset(
    study_id: str,
    dataset_id: str,
    request: Request,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Re-fetch URL dataset in a study and refresh statistics only if changed."""
    await _verify_study_access(study_id, current_user, session, write=True)
    user_id = current_user.id if current_user else None
    # Child-parent check: passing the gate for THIS study must not let a caller
    # refresh a dataset that hangs off another one.
    existing = await service.get_dataset(dataset_id, user_id=user_id)
    if not existing or existing.study_id != study_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    await session.rollback()
    return await _refresh_command(request, service, dataset_id, current_user.id)


@router.delete("/studies/{study_id}/datasets/{dataset_id}")
async def delete_study_dataset(
    study_id: str,
    dataset_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(_get_session),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Delete a dataset from a study."""
    await _verify_study_access(study_id, current_user, session, write=True)
    user_id = current_user.id if current_user else None
    # Child-parent check: the study gate says nothing about which study this
    # dataset actually belongs to.
    existing = await service.get_dataset(dataset_id, user_id=user_id)
    if not existing or existing.study_id != study_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    ok = await service.delete_dataset(dataset_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return {"status": "deleted", "id": dataset_id}
