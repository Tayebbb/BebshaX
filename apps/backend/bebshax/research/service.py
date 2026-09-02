"""Research engine service orchestrating end-to-end autonomous research runs, evidence analytics, and dataset discovery.

Coordinates research plan generation, query formulation, evidence source collection,
document chunking, pgvector embedding, claim extraction, public dataset discovery,
relevance evaluation, and automated dataset ingestion.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.segmenter import discover_segments
from bebshax.db.models import (
    DatasetCandidates,
    DatasetSources,
    EvidenceChunks,
    EvidenceClaims,
    EvidenceSources,
    ResearchPlans,
    ResearchRuns,
    Studies,
    _utcnow,
)
from bebshax.llm.service import LLMService
from bebshax.research.chunker import chunk_document
from bebshax.research.claim_extractor import (
    extract_claims_with_llm,
    extract_deterministic_claims,
)
from bebshax.research.planner import (
    ResearchPlanResult,
    generate_structured_research_plan,
)
from bebshax.research.query_generator import generate_research_queries
from bebshax.research.search_provider import (
    CuratedResearchProvider,
    SearchProvider,
)
from bebshax.research.vector_search import VectorSearchEngine
from bebshax.config import get_settings
from bebshax.tenancy import ANONYMOUS_OWNER_ID


def _upload_dir() -> Path:
    """Configured upload root (BEBSHAX_UPLOAD_DIR / BEBSHAX_DATA_DIR), resolved at call time."""
    return get_settings().upload_dir_path


class ResearchEngineService:
    """Orchestrates autonomous end-to-end research runs across evidence and public datasets."""

    def __init__(
        self,
        search_provider: Optional[SearchProvider] = None,
        vector_engine: Optional[VectorSearchEngine] = None,
        llm_service: Optional[LLMService] = None,
        discovery_engine: Optional[DatasetDiscoveryEngine] = None,
    ) -> None:
        self.search_provider = search_provider or CuratedResearchProvider()
        self.vector_engine = vector_engine or VectorSearchEngine()
        self.llm_service = llm_service
        self.discovery_engine = discovery_engine or DatasetDiscoveryEngine()
        _upload_dir().mkdir(parents=True, exist_ok=True)

    async def run_study_research(
        self,
        session: AsyncSession,
        study: Studies,
        user_id: Optional[str] = None,
    ) -> ResearchRuns:
        """Execute an autonomous research run for a study, generating research plans, evidence, and discovered datasets."""
        effective_user_id = user_id or study.user_id or ANONYMOUS_OWNER_ID
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        prompt = study.prompt or study.title

        step_progress: dict[str, Any] = {
            "understanding_idea": {"status": "in_progress", "label": "Understanding business idea"},
            "building_research_plan": {"status": "pending", "label": "Building research plan"},
            "searching_evidence": {"status": "pending", "label": "Searching evidence sources"},
            "discovering_datasets": {"status": "pending", "label": "Discovering public datasets"},
            "evaluating_datasets": {"status": "pending", "label": "Evaluating dataset quality & relevance"},
            "importing_datasets": {"status": "pending", "label": "Processing & profiling datasets"},
            "extracting_evidence": {"status": "pending", "label": "Synthesizing evidence claims"},
        }

        run = ResearchRuns(
            id=run_id,
            study_id=study.id,
            user_id=effective_user_id,
            status="understanding_idea",
            current_step="understanding_idea",
            step_progress=step_progress,
            started_at=datetime.datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        try:
            # -------------------------------------------------------------
            # STEP 1: Understand Business Idea & Generate Research Plan
            # -------------------------------------------------------------
            run.current_step = "building_research_plan"
            step_progress["understanding_idea"]["status"] = "completed"
            step_progress["building_research_plan"]["status"] = "in_progress"
            run.step_progress = step_progress
            await session.commit()

            plan_result: ResearchPlanResult = await generate_structured_research_plan(
                idea=prompt,
                target_audience=study.target_audience,
                pricing_hypothesis=study.pricing_hypothesis,
                llm_service=self.llm_service,
            )

            # Persist ResearchPlan in database
            plan_id = f"plan_{uuid.uuid4().hex[:16]}"
            plan_record = ResearchPlans(
                id=plan_id,
                study_id=study.id,
                user_id=effective_user_id,
                run_id=run_id,
                business_idea=prompt,
                target_market=plan_result.target_market,
                problem_areas=plan_result.problem_areas,
                behavioral_questions=plan_result.behavioral_questions,
                economic_questions=plan_result.economic_questions,
                competition_questions=plan_result.competition_questions,
                market_questions=plan_result.market_questions,
                dataset_requirements=[r.model_dump() for r in plan_result.dataset_requirements],
                summary=plan_result.summary,
            )
            session.add(plan_record)
            run.research_plan = plan_result.model_dump()
            step_progress["building_research_plan"]["status"] = "completed"

            # -------------------------------------------------------------
            # STEP 2: Generate Search Queries & Discover Evidence Sources
            # -------------------------------------------------------------
            run.current_step = "searching_evidence"
            step_progress["searching_evidence"]["status"] = "in_progress"
            run.step_progress = step_progress
            await session.commit()

            queries = await generate_research_queries(
                idea=prompt,
                target_audience=study.target_audience,
                pricing_hypothesis=study.pricing_hypothesis,
                llm_service=self.llm_service,
            )
            run.queries = queries
            run.query_count = len(queries)

            discovered_sources = await self.search_provider.search(queries)
            run.source_count = len(discovered_sources)

            # Chunk, embed, and store sources
            sources_to_insert: list[EvidenceSources] = []
            chunks_to_insert: list[EvidenceChunks] = []
            all_chunks_meta: list[tuple] = []  # (source_id, discovered_source, raw_chunks)
            all_raw_chunks: list[str] = []

            for d in discovered_sources:
                source_id = f"src_{uuid.uuid4().hex[:16]}"
                source = EvidenceSources(
                    id=source_id,
                    study_id=study.id,
                    user_id=effective_user_id,
                    run_id=run_id,
                    source_type=d.source_type,
                    title=d.title,
                    url=d.url,
                    publisher=d.publisher,
                    content=d.content,
                    content_hash=d.content_hash,
                    relevance_score=d.relevance_score,
                    status="processed",
                    metadata_payload=d.metadata,
                )
                sources_to_insert.append(source)

                raw_chunks_for_source = chunk_document(d.content, chunk_size=400, chunk_overlap=40)
                if not raw_chunks_for_source:
                    raw_chunks_for_source = [d.content[:400]]
                all_chunks_meta.append((source_id, d, raw_chunks_for_source))
                all_raw_chunks.extend(raw_chunks_for_source)

            # One embed_texts call covers all sources — avoids N sequential
            # round-trips. Skipped entirely when there is nothing to embed:
            # some backends reject an empty batch.
            if all_raw_chunks:
                all_embeddings = await self.vector_engine.embed_texts(all_raw_chunks)
                if len(all_embeddings) != len(all_raw_chunks):
                    raise RuntimeError(
                        "embedding backend returned "
                        f"{len(all_embeddings)} vectors for {len(all_raw_chunks)} chunks"
                    )
                emb_iter = iter(all_embeddings)
                for source_id, d, raw_chunks in all_chunks_meta:
                    for idx, chunk_text in enumerate(raw_chunks):
                        emb = next(emb_iter)
                        chunk_id = f"chk_{uuid.uuid4().hex[:16]}"
                        chunk = EvidenceChunks(
                            id=chunk_id,
                            source_id=source_id,
                            study_id=study.id,
                            chunk_index=idx,
                            content=chunk_text,
                            embedding=emb,
                            embedding_space=self.vector_engine.backend.space,
                            metadata_payload={"source_title": d.title, "publisher": d.publisher},
                        )
                        chunks_to_insert.append(chunk)

            session.add_all(sources_to_insert)
            session.add_all(chunks_to_insert)
            step_progress["searching_evidence"]["status"] = "completed"

            # -------------------------------------------------------------
            # STEP 3: Discover, Evaluate & Auto-Import Public Datasets
            # -------------------------------------------------------------
            run.current_step = "discovering_datasets"
            step_progress["discovering_datasets"]["status"] = "in_progress"
            run.step_progress = step_progress
            await session.commit()

            try:
                candidates, imported_ds = await self.discovery_engine.discover_and_process_datasets(
                    session=session,
                    study_id=study.id,
                    user_id=effective_user_id,
                    run_id=run_id,
                    idea=prompt,
                    queries=queries,
                    requirements=plan_result.dataset_requirements,
                )
                run.dataset_candidate_count = len(candidates)
                run.dataset_imported_count = len(imported_ds)
                step_progress["discovering_datasets"]["status"] = "completed"
                step_progress["evaluating_datasets"]["status"] = "completed"
                step_progress["importing_datasets"]["status"] = "completed"
            except Exception as ds_err:
                step_progress["discovering_datasets"]["status"] = "completed_with_warnings"
                step_progress["evaluating_datasets"]["status"] = "completed_with_warnings"
                step_progress["importing_datasets"]["status"] = "completed_with_warnings"

            # -------------------------------------------------------------
            # STEP 4: Extract Empirical Claims
            # -------------------------------------------------------------
            run.current_step = "extracting_evidence"
            step_progress["extracting_evidence"]["status"] = "in_progress"
            run.step_progress = step_progress
            await session.commit()

            if self.llm_service:
                claims_data = await extract_claims_with_llm(
                    idea=prompt,
                    sources=sources_to_insert,
                    chunks=chunks_to_insert,
                    llm_service=self.llm_service,
                )
            else:
                claims_data = extract_deterministic_claims(
                    idea=prompt,
                    sources=sources_to_insert,
                    chunks=chunks_to_insert,
                )

            claims_to_insert: list[EvidenceClaims] = []
            for cd in claims_data:
                claim_id = cd.get("id") or f"claim_{uuid.uuid4().hex[:16]}"
                claim = EvidenceClaims(
                    id=claim_id,
                    study_id=study.id,
                    user_id=effective_user_id,
                    run_id=run_id,
                    claim_text=cd["claim_text"],
                    status=cd["status"],
                    category=cd.get("category", "general"),
                    confidence=cd.get("confidence", 0.75),
                    supporting_source_ids=cd.get("supporting_source_ids", []),
                    supporting_chunk_ids=cd.get("supporting_chunk_ids", []),
                    contradicting_source_ids=cd.get("contradicting_source_ids", []),
                    rationale=cd.get("rationale"),
                )
                claims_to_insert.append(claim)

            session.add_all(claims_to_insert)
            run.claim_count = len(claims_to_insert)
            step_progress["extracting_evidence"]["status"] = "completed"

            # Finalize run
            run.status = "completed"
            run.current_step = "completed"
            run.step_progress = step_progress
            run.completed_at = datetime.datetime.now(timezone.utc)
            study.status = "in_progress"
            await session.commit()
            await session.refresh(run)
            return run

        except Exception as exc:
            run.status = "failed"
            run.current_step = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(run)
            return run

    async def get_research_plan(
        self,
        session: AsyncSession,
        study_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve latest structured research plan for a study."""
        stmt = select(ResearchPlans).where(ResearchPlans.study_id == study_id).order_by(ResearchPlans.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        plan = res.scalar_one_or_none()
        if not plan:
            return None
        return {
            "id": plan.id,
            "study_id": plan.study_id,
            "business_idea": plan.business_idea,
            "target_market": plan.target_market,
            "problem_areas": plan.problem_areas,
            "behavioral_questions": plan.behavioral_questions,
            "economic_questions": plan.economic_questions,
            "competition_questions": plan.competition_questions,
            "market_questions": plan.market_questions,
            "dataset_requirements": plan.dataset_requirements,
            "summary": plan.summary,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
        }

    async def list_dataset_candidates(
        self,
        session: AsyncSession,
        study_id: str,
    ) -> list[dict[str, Any]]:
        """List discovered dataset candidates for a study."""
        stmt = select(DatasetCandidates).where(DatasetCandidates.study_id == study_id).order_by(DatasetCandidates.relevance_score.desc())
        res = await session.execute(stmt)
        candidates = list(res.scalars().all())
        return [
            {
                "id": c.id,
                "study_id": c.study_id,
                "run_id": c.run_id,
                "source": c.source,
                "external_id": c.external_id,
                "name": c.name,
                "description": c.description,
                "url": c.url,
                "download_url": c.download_url,
                "publisher": c.publisher,
                "license": c.license,
                "license_url": c.license_url,
                "format": c.format,
                "size_bytes": c.size_bytes,
                "sample_rows": c.sample_rows,
                "sample_columns": c.sample_columns,
                "geographic_coverage": c.geographic_coverage,
                "population_coverage": c.population_coverage,
                "relevant_variables": c.relevant_variables,
                "relevance_score": c.relevance_score,
                "quality_score": c.quality_score,
                "selection_status": c.selection_status,
                "selection_reason": c.selection_reason,
                "evaluation_details": c.evaluation_details,
                "is_sample": bool((c.evaluation_details or {}).get("is_sample", False)),
                "imported_dataset_id": c.imported_dataset_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in candidates
        ]

    async def import_candidate_dataset(
        self,
        session: AsyncSession,
        study_id: str,
        candidate_id: str,
        user_id: str,
    ) -> DatasetSources:
        """Manually trigger import of a discovered dataset candidate into dataset_sources."""
        stmt = select(DatasetCandidates).where(
            DatasetCandidates.id == candidate_id,
            DatasetCandidates.study_id == study_id,
        )
        res = await session.execute(stmt)
        candidate = res.scalar_one_or_none()
        if not candidate:
            raise ValueError("Dataset candidate not found")

        # Ingest candidate into DatasetSources
        raw_csv = (
            "id,category,value_bdt,score,timestamp\n"
            + "\n".join(f"ROW_{100 + i},Category_{i % 3},{500 + i * 50},{70.0 + (i % 25)},2024-01-01" for i in range(100))
        )
        content_bytes = raw_csv.encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        columns, rows = parse_dataset_bytes(content_bytes, file_type=candidate.format or "csv")
        schema_metadata, stats = profile_dataset(columns, rows)
        segments = discover_segments(columns, rows, schema_metadata, stats)

        ds_id = f"ds_{uuid.uuid4().hex[:16]}"
        file_path = str(_upload_dir() / f"{ds_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(rows, f)

        imported_ds = DatasetSources(
            id=ds_id,
            user_id=user_id,
            study_id=study_id,
            name=candidate.name,
            source_type="url",
            source_url=candidate.url,
            file_path=file_path,
            file_type=candidate.format or "csv",
            description=(
                f"{candidate.description}"
                "\n\nIllustrative sample catalog — modeled on public sources, not fetched live."
                f"\n\nSource: {candidate.source} ({candidate.publisher}) | License: {candidate.license}"
            ),
            status="ready",
            row_count=len(rows),
            column_count=len(columns),
            # The imported content is generated placeholder rows, never a live
            # fetch — always mark it as a sample.
            schema_metadata={**schema_metadata, "is_sample": True},
            statistics=stats,
            segments=segments,
            content_hash=content_hash,
            persona_count_generated=0,
            last_processed_at=_utcnow(),
        )
        session.add(imported_ds)
        candidate.imported_dataset_id = ds_id
        candidate.selection_status = "imported"
        await session.commit()
        await session.refresh(imported_ds)
        return imported_ds

    async def reject_candidate_dataset(
        self,
        session: AsyncSession,
        study_id: str,
        candidate_id: str,
    ) -> bool:
        """Mark a dataset candidate as rejected by user so it is not auto-selected."""
        stmt = select(DatasetCandidates).where(
            DatasetCandidates.id == candidate_id,
            DatasetCandidates.study_id == study_id,
        )
        res = await session.execute(stmt)
        candidate = res.scalar_one_or_none()
        if not candidate:
            raise ValueError("Dataset candidate not found")
        candidate.selection_status = "rejected_by_user"
        await session.commit()
        return True

    async def get_evidence_summary(
        self,
        session: AsyncSession,
        study_id: str,
    ) -> dict[str, Any]:
        """Calculate evidence coverage, candidates count, and research summary from database."""
        claims_stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
        claims_result = await session.execute(claims_stmt)
        claims = list(claims_result.scalars().all())

        sources_count_stmt = select(func.count(EvidenceSources.id)).where(EvidenceSources.study_id == study_id)
        sources_count_result = await session.execute(sources_count_stmt)
        source_count = sources_count_result.scalar() or 0

        candidates_count_stmt = select(func.count(DatasetCandidates.id)).where(DatasetCandidates.study_id == study_id)
        candidates_count_result = await session.execute(candidates_count_stmt)
        candidates_count = candidates_count_result.scalar() or 0

        imported_ds_count_stmt = select(func.count(DatasetSources.id)).where(DatasetSources.study_id == study_id)
        imported_ds_count_result = await session.execute(imported_ds_count_stmt)
        imported_ds_count = imported_ds_count_result.scalar() or 0

        run_stmt = select(ResearchRuns).where(ResearchRuns.study_id == study_id).order_by(ResearchRuns.created_at.desc()).limit(1)
        run_result = await session.execute(run_stmt)
        latest_run = run_result.scalar_one_or_none()

        total_claims = len(claims)
        supported_count = sum(1 for c in claims if c.status == "supported")
        inferred_count = sum(1 for c in claims if c.status == "inference")
        unsupported_count = sum(1 for c in claims if c.status == "unsupported")

        supported_pct = round((supported_count / total_claims) * 100) if total_claims > 0 else 0
        inferred_pct = round((inferred_count / total_claims) * 100) if total_claims > 0 else 0
        unsupported_pct = round((unsupported_count / total_claims) * 100) if total_claims > 0 else 0
        evidence_coverage = supported_pct

        return {
            "study_id": study_id,
            "research_status": latest_run.status if latest_run else "idle",
            "current_step": latest_run.current_step if latest_run else "idle",
            "step_progress": latest_run.step_progress if latest_run else {},
            "evidence_coverage": evidence_coverage,
            "supported_pct": supported_pct,
            "inferred_pct": inferred_pct,
            "unsupported_pct": unsupported_pct,
            "supported_count": supported_count,
            "inferred_count": inferred_count,
            "unsupported_count": unsupported_count,
            "total_claims": total_claims,
            "total_sources": source_count,
            "total_candidates": candidates_count,
            "total_imported_datasets": imported_ds_count,
            "latest_run": {
                "id": latest_run.id,
                "status": latest_run.status,
                "current_step": latest_run.current_step,
                "query_count": latest_run.query_count,
                "source_count": latest_run.source_count,
                "claim_count": latest_run.claim_count,
                "dataset_candidate_count": latest_run.dataset_candidate_count,
                "dataset_imported_count": latest_run.dataset_imported_count,
                "step_progress": latest_run.step_progress,
                "research_plan": latest_run.research_plan,
                "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
                "error_message": latest_run.error_message,
            } if latest_run else None,
        }
