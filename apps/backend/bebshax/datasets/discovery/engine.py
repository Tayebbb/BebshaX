"""Dataset Discovery Engine orchestrating search, evaluation, persistence, and automated ingestion.

Sources are live and keyless (World Bank Open Data, HDX, data.gov). A selected
candidate is imported by downloading its published resource within the
downloader's budgets and running it through the normal parse → profile →
segment pipeline; nothing is generated in place of a download.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.config import get_settings
from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetSourceAdapter
from bebshax.datasets.discovery.ckan_adapter import CKANDatasetAdapter
from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes, looks_downloadable
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter
from bebshax.datasets.parser import DatasetParseError, detect_format, parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.segmenter import discover_segments
from bebshax.db.models import DatasetCandidates, DatasetSources, _utcnow
from bebshax.research.planner import DatasetRequirementSpec

logger = logging.getLogger(__name__)


def _upload_dir() -> Path:
    """Configured upload root (BEBSHAX_UPLOAD_DIR / BEBSHAX_DATA_DIR), resolved at call time."""
    return get_settings().upload_dir_path


def default_adapters(http_client: httpx.AsyncClient | None = None) -> list[DatasetSourceAdapter]:
    return [
        WorldBankOpenDataAdapter(http_client=http_client),
        CKANDatasetAdapter.hdx(http_client=http_client),
        CKANDatasetAdapter.datagov(http_client=http_client),
    ]


async def materialize_candidate(
    *,
    session: AsyncSession,
    study_id: str,
    user_id: str,
    name: str,
    description: str,
    source: str,
    publisher: str,
    license_text: str,
    url: Optional[str],
    download_url: Optional[str],
    declared_format: Optional[str],
    raw_data_content: Optional[str] = None,
    http_client: httpx.AsyncClient | None = None,
) -> DatasetSources:
    """Turn a discovered candidate into a real ``DatasetSources`` row by fetching
    its published resource (or using content already fetched from an API) and
    running the standard parse/profile/segment pipeline.

    Raises ``DatasetDownloadFailed`` (no resource URL, network, size, HTTP) or
    ``DatasetParseError`` — never substitutes generated rows.
    """
    if raw_data_content:
        content_bytes = raw_data_content.encode("utf-8")
        fetched_from = download_url or url or source
        content_type = "text/csv"
    else:
        if not looks_downloadable(download_url):
            raise DatasetDownloadFailed(
                f"'{name}' has no direct download resource published; open the listing and upload the file manually.",
                extra={"url": url},
            )
        content_bytes, meta = await fetch_resource_bytes(download_url, http_client=http_client)  # type: ignore[arg-type]
        fetched_from = meta["url"]
        content_type = meta["content_type"]

    file_type = (declared_format or "").lower() or detect_format(content_bytes, filename=fetched_from, content_type=content_type)
    columns, rows = parse_dataset_bytes(content_bytes, file_type=file_type, filename=fetched_from, content_type=content_type)
    schema_metadata, stats = profile_dataset(columns, rows)
    segments = discover_segments(columns, rows, schema_metadata, stats)
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    ds_id = f"ds_{uuid.uuid4().hex[:16]}"
    file_path = str(_upload_dir() / f"{ds_id}.json")
    _upload_dir().mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(rows, f)

    imported = DatasetSources(
        id=ds_id,
        user_id=user_id,
        study_id=study_id,
        name=name,
        source_type="url",
        source_url=url or download_url,
        file_path=file_path,
        file_type=file_type,
        description=(
            f"{description}\n\nSource: {source} ({publisher}) | License: {license_text or 'not stated'}"
            f"\nFetched from: {fetched_from}"
        ),
        status="ready",
        row_count=len(rows),
        column_count=len(columns),
        schema_metadata={**schema_metadata, "is_sample": False, "fetched_from": fetched_from},
        statistics=stats,
        segments=segments,
        content_hash=content_hash,
        persona_count_generated=0,
        last_processed_at=_utcnow(),
    )
    session.add(imported)
    return imported


class DatasetDiscoveryEngine:
    """Coordinates public dataset search across adapters, evaluation, and automatic ingestion."""

    def __init__(
        self,
        adapters: Optional[list[DatasetSourceAdapter]] = None,
        evaluator: Optional[DatasetEvaluator] = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._http_client = http_client
        self.adapters = adapters if adapters is not None else default_adapters(http_client)
        self.evaluator = evaluator or DatasetEvaluator(max_auto_select=4)

    async def discover_and_process_datasets(
        self,
        session: AsyncSession,
        study_id: str,
        user_id: str,
        run_id: str,
        idea: str,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
        countries: Optional[list[str]] = None,
    ) -> tuple[list[DatasetCandidates], list[DatasetSources]]:
        """Search public repositories, evaluate candidates, auto-import top datasets, and persist state."""
        all_raw_candidates: list[DatasetCandidateData] = []
        for adapter in self.adapters:
            try:
                found = await adapter.search(queries, requirements, countries=countries)
                all_raw_candidates.extend(found)
            except Exception as exc:
                logger.warning("Adapter %s search failed: %s", adapter.source_name, type(exc).__name__)

        evaluated_results = self.evaluator.evaluate_candidates(all_raw_candidates, idea, requirements, queries)

        saved_candidates: list[DatasetCandidates] = []
        imported_sources: list[DatasetSources] = []

        for eval_res in evaluated_results:
            cand = eval_res.candidate
            db_cand = DatasetCandidates(
                id=f"cand_{uuid.uuid4().hex[:16]}",
                study_id=study_id,
                user_id=user_id,
                run_id=run_id,
                source=cand.source,
                external_id=cand.external_id,
                name=cand.name,
                description=cand.description,
                url=cand.url,
                download_url=cand.download_url,
                publisher=cand.publisher,
                license=cand.license,
                license_url=cand.license_url,
                format=cand.format,
                size_bytes=cand.size_bytes,
                sample_rows=cand.sample_rows,
                sample_columns=cand.sample_columns,
                geographic_coverage=cand.geographic_coverage,
                population_coverage=cand.population_coverage,
                relevant_variables=cand.relevant_variables,
                relevance_score=eval_res.relevance_score,
                quality_score=eval_res.quality_score,
                selection_status=eval_res.selection_status,
                selection_reason=eval_res.selection_reason,
                evaluation_details={
                    **eval_res.evaluation_details,
                    "is_sample": cand.is_sample,
                    "tags": cand.tags,
                    "modified_at": cand.modified_at,
                },
            )

            metadata_errors = {}
            for column in DatasetCandidates.__table__.columns:
                if column.name not in DatasetCandidateData.model_fields:
                    continue
                value = getattr(cand, column.name)
                limit = column.type.length if isinstance(column.type, String) else None
                if isinstance(value, str) and limit is not None and len(value) > limit:
                    metadata_errors[column.name] = {"actual_length": len(value), "max_length": limit}
                    replacement = (
                        "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
                        if column.name in {"source", "external_id"}
                        else f"See evaluation_details.raw_metadata.{column.name}"
                    )
                    setattr(db_cand, column.name, replacement)

            if metadata_errors:
                fields = ", ".join(
                    f"{field}: {bounds['actual_length']} > {bounds['max_length']} characters"
                    for field, bounds in metadata_errors.items()
                )
                detail = (
                    f"Not imported: dataset metadata exceeds storage limits ({fields}). "
                    "Full candidate preserved in evaluation_details.raw_metadata."
                )
                db_cand.selection_status = "import_failed"
                db_cand.selection_reason = f"{detail}\n{eval_res.selection_reason}"
                db_cand.evaluation_details = {
                    **db_cand.evaluation_details,
                    "raw_metadata": cand.model_dump(mode="json"),
                    "metadata_errors": metadata_errors,
                    "import_error": detail,
                }
                logger.warning("Dataset candidate metadata rejected: %s", fields)

            if eval_res.is_selected and not metadata_errors:
                try:
                    imported_ds = await materialize_candidate(
                        session=session,
                        study_id=study_id,
                        user_id=user_id,
                        name=cand.name,
                        description=cand.description,
                        source=cand.source,
                        publisher=cand.publisher,
                        license_text=cand.license,
                        url=cand.url,
                        download_url=cand.download_url,
                        declared_format=cand.format,
                        raw_data_content=cand.raw_data_content,
                        http_client=self._http_client,
                    )
                    db_cand.imported_dataset_id = imported_ds.id
                    db_cand.selection_status = "imported"
                    db_cand.sample_rows = imported_ds.row_count
                    db_cand.sample_columns = imported_ds.column_count
                    imported_sources.append(imported_ds)
                except (DatasetDownloadFailed, DatasetParseError) as exc:
                    detail = exc.detail if isinstance(exc, DatasetDownloadFailed) else str(exc)
                    logger.info("candidate %s not imported: %s", cand.name, detail)
                    db_cand.selection_status = "import_failed"
                    db_cand.evaluation_details = {**db_cand.evaluation_details, "import_error": detail}
                except Exception as exc:
                    logger.warning("candidate %s import crashed: %s", cand.name, type(exc).__name__, exc_info=True)
                    db_cand.selection_status = "import_failed"
                    db_cand.evaluation_details = {**db_cand.evaluation_details, "import_error": type(exc).__name__}

            saved_candidates.append(db_cand)
            session.add(db_cand)

        await session.commit()
        return saved_candidates, imported_sources
