"""FastAPI endpoints for Dataset Sources, deterministic profiling, and evidence-grounded persona generation."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Header, Request, UploadFile, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.auth.security import decode_access_token
from bebshax.datasets.service import DatasetService
from bebshax.db.engine import get_session
from bebshax.db.models import DatasetSources

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _extract_user_id(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    payload = decode_access_token(token)
    return payload.get("sub") if payload else None


def _get_dataset_service(request: Request) -> DatasetService:
    sessionmaker_: Optional[sessionmaker[AsyncSession]] = getattr(request.app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        from bebshax.config import get_settings
        from bebshax.db.engine import create_async_sessionmaker, create_engine
        settings = get_settings()
        engine = create_engine(settings)
        sessionmaker_ = create_async_sessionmaker(engine)
    return DatasetService(sessionmaker_)


class IngestUrlRequest(BaseModel):
    url: str
    name: str
    description: Optional[str] = None
    study_id: Optional[str] = None
    file_type: Optional[str] = None


class QueryDatasetRequest(BaseModel):
    filter_col: Optional[str] = None
    filter_val: Optional[Any] = None
    limit: int = 100


class GeneratePersonasRequest(BaseModel):
    requested_count: int = 10
    study_id: Optional[str] = None
    business_name: str = "BebshaX Research Initiative"
    business_description: str = "Evidence-grounded user interview validation"


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
        "persona_count_generated": ds.persona_count_generated,
        "processing_error": ds.processing_error,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        "last_processed_at": ds.last_processed_at.isoformat() if ds.last_processed_at else None,
    }


@router.get("")
async def list_datasets(
    user_id: Optional[str] = Depends(_extract_user_id),
    service: DatasetService = Depends(_get_dataset_service),
) -> list[dict[str, Any]]:
    """List all available datasets for the current user."""
    datasets = await service.list_datasets(user_id=user_id)
    return [_serialize_dataset(ds) for ds in datasets]


@router.post("/url", status_code=status.HTTP_201_CREATED)
async def ingest_dataset_url(
    payload: IngestUrlRequest,
    user_id: Optional[str] = Depends(_extract_user_id),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Fetch external dataset from URL with SSRF validation, parse, profile, and derive segments."""
    try:
        ds = await service.ingest_from_url(
            url=payload.url,
            name=payload.name,
            description=payload.description,
            user_id=user_id,
            study_id=payload.study_id,
            file_type=payload.file_type,
        )
        return _serialize_dataset(ds)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset ingestion failed: {exc}",
        ) from exc


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    study_id: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    user_id: Optional[str] = Depends(_extract_user_id),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Upload a dataset file (CSV, JSON, TSV, XLSX) to profile and derive segments."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        ds = await service.ingest_from_upload(
            content=content,
            original_filename=file.filename or "dataset.csv",
            name=name,
            description=description,
            user_id=user_id,
            study_id=study_id,
            file_type=file_type,
        )
        return _serialize_dataset(ds)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded dataset processing failed: {exc}",
        ) from exc


@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Get full dataset profile, schema metadata, descriptive statistics, and discovered segments."""
    ds = await service.get_dataset(dataset_id)
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return _serialize_dataset(ds)


@router.post("/{dataset_id}/refresh")
async def refresh_dataset(
    dataset_id: str,
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Re-fetch URL-based dataset and update schema, statistics, and segments."""
    try:
        ds = await service.refresh_dataset(dataset_id)
        if not ds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dataset cannot be refreshed (not a URL source or not found).",
            )
        return _serialize_dataset(ds)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Refresh failed: {exc}") from exc


@router.post("/{dataset_id}/query")
async def query_dataset(
    dataset_id: str,
    payload: QueryDatasetRequest,
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Execute deterministic queries and filters against stored dataset records."""
    return await service.query_dataset(
        dataset_id=dataset_id,
        filter_col=payload.filter_col,
        filter_val=payload.filter_val,
        limit=payload.limit,
    )


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    user_id: Optional[str] = Depends(_extract_user_id),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Delete dataset source."""
    ok = await service.delete_dataset(dataset_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return {"status": "deleted", "id": dataset_id}


@router.post("/{dataset_id}/generate-personas")
async def generate_personas_from_dataset(
    dataset_id: str,
    payload: GeneratePersonasRequest,
    user_id: Optional[str] = Depends(_extract_user_id),
    service: DatasetService = Depends(_get_dataset_service),
) -> dict[str, Any]:
    """Generate synthetic personas strictly grounded in dataset segment distributions and constraints."""
    try:
        return await service.generate_personas_from_dataset(
            dataset_id=dataset_id,
            requested_count=payload.requested_count,
            user_id=user_id,
            study_id=payload.study_id,
            business_name=payload.business_name,
            business_description=payload.business_description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persona generation failed: {exc}",
        ) from exc
