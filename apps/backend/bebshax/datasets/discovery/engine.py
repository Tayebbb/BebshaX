"""Dataset Discovery Engine orchestrating search, evaluation, persistence, and automated ingestion."""

from __future__ import annotations

import datetime
from datetime import timezone
import logging
import uuid
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetEvaluationResult, DatasetSourceAdapter
from bebshax.datasets.discovery.bbs_adapter import BBSOpenDataAdapter
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.datasets.discovery.kaggle_adapter import KaggleOpenDataAdapter
from bebshax.datasets.discovery.world_bank_adapter import WorldBankOpenDataAdapter
from bebshax.datasets.service import DatasetService
from bebshax.db.models import DatasetCandidates, DatasetSources
from bebshax.research.planner import DatasetRequirementSpec

logger = logging.getLogger(__name__)


from pathlib import Path
import hashlib
import json

from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.segmenter import discover_segments
from bebshax.config import get_settings
from bebshax.db.models import _utcnow


def _upload_dir() -> Path:
    """Configured upload root (BEBSHAX_UPLOAD_DIR / BEBSHAX_DATA_DIR), resolved at call time."""
    return get_settings().upload_dir_path


class DatasetDiscoveryEngine:
    """Coordinates public dataset search across adapters, evaluation, and automatic ingestion."""

    def __init__(
        self,
        adapters: Optional[list[DatasetSourceAdapter]] = None,
        evaluator: Optional[DatasetEvaluator] = None,
    ) -> None:
        self.adapters = adapters or [
            BBSOpenDataAdapter(),
            WorldBankOpenDataAdapter(),
            KaggleOpenDataAdapter(),
        ]
        self.evaluator = evaluator or DatasetEvaluator(max_auto_select=4)
        _upload_dir().mkdir(parents=True, exist_ok=True)

    async def discover_and_process_datasets(
        self,
        session: AsyncSession,
        study_id: str,
        user_id: str,
        run_id: str,
        idea: str,
        queries: list[str],
        requirements: list[DatasetRequirementSpec],
    ) -> tuple[list[DatasetCandidates], list[DatasetSources]]:
        """Search public repositories, evaluate candidates, auto-import top datasets, and persist state."""
        # 1. Search all adapters in parallel
        all_raw_candidates: list[DatasetCandidateData] = []
        for adapter in self.adapters:
            try:
                found = await adapter.search(queries, requirements)
                all_raw_candidates.extend(found)
            except Exception as exc:
                logger.warning("Adapter %s search failed: %s", adapter.source_name, exc)

        # 2. Evaluate and select top candidates
        evaluated_results = self.evaluator.evaluate_candidates(all_raw_candidates, idea, requirements)

        # 3. Persist Candidate records & Auto-Import selected datasets
        saved_candidates: list[DatasetCandidates] = []
        imported_sources: list[DatasetSources] = []

        for eval_res in evaluated_results:
            cand = eval_res.candidate
            cand_id = f"cand_{uuid.uuid4().hex[:16]}"

            db_cand = DatasetCandidates(
                id=cand_id,
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
                evaluation_details={**eval_res.evaluation_details, "is_sample": cand.is_sample},
            )

            # Auto-import if selected
            if eval_res.is_selected and cand.raw_data_content:
                try:
                    content_bytes = cand.raw_data_content.encode("utf-8")
                    content_hash = hashlib.sha256(content_bytes).hexdigest()
                    columns, rows = parse_dataset_bytes(content_bytes, file_type=cand.format or "csv")
                    schema_metadata, stats = profile_dataset(columns, rows)
                    segments = discover_segments(columns, rows, schema_metadata, stats)

                    ds_id = f"ds_{uuid.uuid4().hex[:16]}"
                    file_path = str(_upload_dir() / f"{ds_id}.json")
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(rows, f)

                    sample_note = (
                        "\n\nIllustrative sample catalog — modeled on public sources, not fetched live."
                        if cand.is_sample
                        else ""
                    )
                    imported_ds = DatasetSources(
                        id=ds_id,
                        user_id=user_id,
                        study_id=study_id,
                        name=cand.name,
                        source_type="url",
                        source_url=cand.url,
                        file_path=file_path,
                        file_type=cand.format or "csv",
                        description=f"{cand.description}{sample_note}\n\nSource: {cand.source} ({cand.publisher}) | License: {cand.license}",
                        status="ready",
                        row_count=len(rows),
                        column_count=len(columns),
                        schema_metadata={**schema_metadata, "is_sample": cand.is_sample},
                        statistics=stats,
                        segments=segments,
                        content_hash=content_hash,
                        persona_count_generated=0,
                        last_processed_at=_utcnow(),
                    )
                    session.add(imported_ds)
                    db_cand.imported_dataset_id = ds_id
                    db_cand.selection_status = "imported"
                    imported_sources.append(imported_ds)
                except Exception as exc:
                    logger.error("Failed to auto-import candidate %s: %s", cand.name, exc)
                    db_cand.selection_status = "import_failed"

            saved_candidates.append(db_cand)
            session.add(db_cand)

        await session.commit()
        return saved_candidates, imported_sources
