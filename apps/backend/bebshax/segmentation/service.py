"""Segmentation Engine Service.

Orchestrates market segmentation lifecycle: pre-checking data, selecting variables,
deterministic clustering, LLM interpretation, evidence linking, and database persistence.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import (
    DatasetSources,
    EvidenceClaims,
    MarketSegments,
    SegmentationRuns,
    Studies,
)
from bebshax.llm.service import LLMService
from bebshax.segmentation.clusterer import SEGMENTATION_REQUIRES_DATA, cluster_dataset_populations
from bebshax.segmentation.interpreter import interpret_market_segments
from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.variable_selector import select_segmentation_variables
from bebshax.utils.explicit_failures import ExplicitFailure, InsufficientInput

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SegmentationEngineService:
    """Core service for orchestrating market segmentation runs."""

    def __init__(self, session: AsyncSession, llm_service: Optional[LLMService] = None):
        self.session = session
        self.llm_service = llm_service

    async def run_segmentation(
        self,
        study_id: str,
        user_id: Optional[str] = None,
        desired_clusters: Optional[int] = None,
        configuration: Optional[dict[str, Any]] = None,
    ) -> tuple[SegmentationRuns, list[MarketSegments]]:
        """Execute full market segmentation for a study."""
        # 1. Fetch study context
        study_res = await self.session.execute(select(Studies).where(Studies.id == study_id))
        study = study_res.scalars().first()
        if not study:
            raise ValueError(f"Study '{study_id}' not found.")

        # 2. Fetch study datasets
        ds_query = select(DatasetSources).where(DatasetSources.study_id == study_id)
        if user_id:
            ds_query = ds_query.where(DatasetSources.user_id == user_id)
        ds_res = await self.session.execute(ds_query)
        datasets = list(ds_res.scalars().all())

        # If no study-specific datasets, fetch global ready datasets for the user
        if not datasets and user_id:
            user_ds_res = await self.session.execute(
                select(DatasetSources).where(DatasetSources.user_id == user_id, DatasetSources.status.in_(("ready", "processed")))
            )
            datasets = list(user_ds_res.scalars().all())

        # 3. Fetch evidence claims
        claims_query = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
        if user_id:
            claims_query = claims_query.where(EvidenceClaims.user_id == user_id)
        claims_res = await self.session.execute(claims_query)
        claims = list(claims_res.scalars().all())

        # 4. Check readiness
        study_ctx = {
            "title": study.title,
            "prompt": study.prompt or study.title,
            "target_audience": study.target_audience or "",
            "pricing_hypothesis": study.pricing_hypothesis or "",
        }
        readiness = check_segmentation_readiness(study_id, datasets, claims, study_ctx)
        if not readiness.can_run:
            raise InsufficientInput(SEGMENTATION_REQUIRES_DATA, readiness.guidance_message)

        # 5. Create segmentation run record
        run_id = f"segrun_{uuid.uuid4().hex[:16]}"
        dataset_versions_payload = [
            {
                "dataset_id": ds.id,
                "name": ds.name,
                "content_hash": ds.content_hash or "unversioned",
                "row_count": ds.row_count,
                "file_type": ds.file_type,
                "is_sample": bool((ds.schema_metadata or {}).get("is_sample", False)),
            }
            for ds in datasets
        ]
        evidence_snapshot_payload = {
            "claim_count": len(claims),
            "top_claims": [
                {"id": c.id, "text": c.claim_text, "category": c.category, "status": c.status}
                for c in claims[:10]
            ],
        }

        config_payload = configuration or {}
        if desired_clusters:
            config_payload["desired_clusters"] = desired_clusters

        seg_run = SegmentationRuns(
            id=run_id,
            study_id=study_id,
            user_id=user_id,
            status="analyzing_data",
            method="hybrid_quantile_clustering",
            configuration=config_payload,
            dataset_versions=dataset_versions_payload,
            evidence_snapshot=evidence_snapshot_payload,
            segment_count=0,
            started_at=_utcnow(),
        )
        self.session.add(seg_run)
        await self.session.commit()

        try:
            # 6. Select candidate variables
            seg_run.status = "selecting_variables"
            await self.session.commit()
            variables = select_segmentation_variables(datasets)

            # 7. Deterministic clustering
            seg_run.status = "clustering"
            await self.session.commit()
            clusters = cluster_dataset_populations(
                datasets=datasets,
                variables=variables,
                claims=claims,
                study_context=study_ctx,
                desired_clusters=desired_clusters,
            )

            # 8. Interpret segments — model-written from the observed statistics
            seg_run.status = "interpreting_segments"
            await self.session.commit()
            interpreted = await interpret_market_segments(
                clusters=clusters,
                study_context=study_ctx,
                claims=claims,
                llm_service=self.llm_service,
            )

            # 9. Persist segments
            created_segments: list[MarketSegments] = []
            for seg in interpreted:
                seg_entity = MarketSegments(
                    id=f"seg_{uuid.uuid4().hex[:16]}",
                    study_id=study_id,
                    user_id=user_id,
                    segmentation_run_id=run_id,
                    name=seg.name,
                    cluster_label=seg.cluster_label,
                    description=seg.description,
                    population_count=seg.population_count,
                    population_percentage=seg.population_percentage,
                    confidence_score=seg.confidence_score,
                    status=seg.status,
                    characteristics=seg.characteristics,
                    variable_distributions=seg.variable_distributions,
                    evidence_citations=seg.evidence_citations,
                    differentiation_summary=seg.differentiation_summary,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                self.session.add(seg_entity)
                created_segments.append(seg_entity)

            # 10. Finalize run
            seg_run.status = "completed"
            seg_run.segment_count = len(created_segments)
            seg_run.completed_at = _utcnow()
            await self.session.commit()
            await self.session.refresh(seg_run)

            return seg_run, created_segments

        except Exception as err:
            seg_run.status = "failed"
            # Explicit failures carry a user-facing message; anything else is
            # reduced to its class name (details go to the server log).
            if isinstance(err, ExplicitFailure):
                seg_run.error_message = err.detail
                seg_run.configuration = {**(seg_run.configuration or {}), "error_code": err.error_code}
            else:
                logger.warning("segmentation run %s failed", run_id, exc_info=True)
                seg_run.error_message = f"Segmentation stopped on an internal error ({type(err).__name__})."
                seg_run.configuration = {**(seg_run.configuration or {}), "error_code": "run_failed"}
            seg_run.completed_at = _utcnow()
            await self.session.commit()
            raise err

    async def get_segment_comparison(
        self,
        study_id: str,
        user_id: Optional[str],
        segment_ids: list[str],
    ) -> dict[str, Any]:
        """Generate a side-by-side comparison structure across 2 to 4 segments."""
        query = select(MarketSegments).where(
            MarketSegments.study_id == study_id,
            MarketSegments.id.in_(segment_ids),
        )
        if user_id:
            query = query.where(MarketSegments.user_id == user_id)

        res = await self.session.execute(query)
        segments = list(res.scalars().all())
        if len(segments) < 2:
            raise ValueError("Select at least 2 valid segments to perform comparison.")

        comparison_matrix = []
        for s in segments:
            chars = s.characteristics or {}
            observed = chars.get("observed") or s.variable_distributions or {}
            partition_variable = chars.get("partition_variable")
            primary = observed.get(partition_variable) if partition_variable else None
            # Only what was measured is shown; absent measurements stay None.
            headline_range = (
                f"{primary['min']:g}–{primary['max']:g}" if isinstance(primary, dict) and "min" in primary else None
            )
            headline_median = primary.get("median") if isinstance(primary, dict) else None
            top_categories = {
                name: dist["top_categories"][0]["category"]
                for name, dist in observed.items()
                if isinstance(dist, dict) and dist.get("top_categories")
            }

            comparison_matrix.append({
                "segment_id": s.id,
                "name": s.name,
                "cluster_label": s.cluster_label,
                "population_count": s.population_count,
                "population_percentage": s.population_percentage,
                "confidence_score": s.confidence_score,
                "status": s.status,
                "partition_variable": partition_variable,
                "headline_range": headline_range,
                "headline_median": headline_median,
                "top_categories": top_categories,
                "observed_variables": sorted(observed.keys()),
                "evidence_citations_count": len(s.evidence_citations or []),
                "differentiation": s.differentiation_summary or s.description,
            })

        return {
            "study_id": study_id,
            "compared_count": len(comparison_matrix),
            "comparison_matrix": comparison_matrix,
        }
