"""Research engine service orchestrating end-to-end autonomous research runs, evidence analytics, and dataset discovery.

Coordinates research plan generation, query formulation, evidence source collection,
document chunking, pgvector embedding, claim extraction, public dataset discovery,
relevance evaluation, and automated dataset ingestion.
"""

from __future__ import annotations

import asyncio
import copy
import datetime
from datetime import timezone
import hashlib
import logging
from pathlib import Path
import uuid
from typing import Any, Optional, cast

from sqlalchemy import String, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from bebshax.api.errors import APIError
from bebshax.datasets.discovery.base_adapter import DatasetCandidateData
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes, looks_downloadable
from bebshax.datasets.orm import DatasetVersions
from bebshax.datasets.parser import DatasetParseError, detect_format
from bebshax.datasets.service import DatasetService
from bebshax.db.models import (
    Base,
    DatasetCandidates,
    DatasetSources,
    EvidenceChunks,
    EvidenceClaims,
    EvidenceSources,
    ResearchPlans,
    ResearchRuns,
    Studies,
)
from bebshax.llm.service import LLMService
from bebshax.llm.failures import LLMError
from bebshax.jobs.runtime import FencedSession, JobContext
from bebshax.jobs.store import LeaseLost
from bebshax.research.chunker import chunk_document
from bebshax.research.claim_extractor import extract_claims_with_llm
from bebshax.research.planner import (
    ResearchPlanResult,
    generate_structured_research_plan,
)
from bebshax.research.query_generator import generate_research_queries
from bebshax.research.search_provider import (
    SearchProvider,
    WikipediaResearchProvider,
)
from bebshax.research.vector_search import VectorSearchEngine
from bebshax.config import get_settings
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.utils.explicit_failures import ExplicitFailure, LLMUnavailable

logger = logging.getLogger(__name__)


def _upload_dir() -> Path:
    """Configured upload root (BEBSHAX_UPLOAD_DIR / BEBSHAX_DATA_DIR), resolved at call time."""
    return get_settings().upload_dir_path


def _safe_error(exc: BaseException) -> tuple[str, str]:
    """(error_code, user-facing message) for a failed run. Internal exception
    text (connection strings, stack details) never reaches the stored record."""
    if isinstance(exc, ExplicitFailure):
        return exc.error_code, exc.detail
    if isinstance(exc, LLMError):
        kind = getattr(exc, "kind", None)
        kind_name = getattr(kind, "value", None) or type(exc).__name__
        return "llm_error", f"The language-model layer failed ({kind_name}); the run was stopped instead of substituting content."
    return "run_failed", f"The research run stopped on an internal error ({type(exc).__name__})."


def _note_served_by(summary: dict[str, Any], served_by: Optional[str]) -> None:
    if served_by and served_by not in summary["served_by"]:
        summary["served_by"].append(served_by)


def _mark_progress(run: ResearchRuns, step_progress: dict[str, Any]) -> None:
    """Persist an in-place-mutated progress dict. SQLAlchemy's JSON column only
    flushes on identity/equality change, so a mutated dict that is re-assigned
    would otherwise be silently dropped."""
    run.step_progress = copy.deepcopy(step_progress)
    flag_modified(run, "step_progress")


def _input_snapshot[Row: Base](row: Row) -> Row:
    return type(row)(**{
        attribute.key: copy.deepcopy(getattr(row, attribute.key))
        for attribute in row.__mapper__.column_attrs
    })


async def _prepare_materialized_candidate(
    storage: DatasetService, *, study_id: str, user_id: str, name: str, description: str,
    source: str, publisher: str, license_text: str, url: str | None, download_url: str | None,
    declared_format: str | None, raw_data_content: str | None = None, http_client: Any = None,
) -> tuple[DatasetSources, DatasetVersions]:
    if raw_data_content:
        content = raw_data_content.encode("utf-8")
        fetched_from, content_type = download_url or url or source, "text/csv"
    else:
        if download_url is None or not looks_downloadable(download_url):
            raise DatasetDownloadFailed("No direct dataset resource is published; upload the source file manually.", extra={"url": url})
        content, metadata = await fetch_resource_bytes(download_url, http_client=http_client)
        fetched_from, content_type = metadata["url"], metadata["content_type"]
    file_type = (declared_format or "").lower() or detect_format(content, filename=fetched_from, content_type=content_type)
    return await storage.prepare_discovered_dataset(
        content=content, study_id=study_id, user_id=user_id, name=name,
        description=f"{description}\n\nSource: {source} ({publisher}) | License: {license_text or 'not stated'}\nFetched from: {fetched_from}",
        source_url=url or download_url, fetched_from=fetched_from, file_type=file_type, content_type=content_type,
    )


async def materialize_candidate(
    *, session: AsyncSession, study_id: str, user_id: str, name: str, description: str,
    source: str, publisher: str, license_text: str, url: str | None, download_url: str | None,
    declared_format: str | None, raw_data_content: str | None = None, http_client: Any = None,
    job: JobContext | None = None,
) -> DatasetSources:
    storage = DatasetService(async_sessionmaker(session.bind, expire_on_commit=False))
    dataset, version = await _prepare_materialized_candidate(
        storage, study_id=study_id, user_id=user_id, name=name, description=description,
        source=source, publisher=publisher, license_text=license_text, url=url, download_url=download_url,
        declared_format=declared_format, raw_data_content=raw_data_content, http_client=http_client,
    )
    try:
        if job is not None:
            await job.fence(session)
        await storage.retain_publication(session, version)
        session.add(dataset)
        await session.flush()
        session.add(version)
        return dataset
    except BaseException:
        await session.rollback()
        await storage._cleanup_uncommitted_versions([version])
        raise


class _VersionedDiscoveryEngine(DatasetDiscoveryEngine):
    def __init__(self, engine: DatasetDiscoveryEngine) -> None:
        super().__init__(adapters=engine.adapters, evaluator=engine.evaluator, http_client=engine._http_client)

    async def discover_and_process_datasets(
        self, session: AsyncSession, study_id: str, user_id: str, run_id: str,
        idea: str, queries: list[str], requirements: list[Any], countries: list[str] | None = None,
    ) -> tuple[list[DatasetCandidates], list[DatasetSources]]:
        if session.in_transaction():
            raise ValueError("Dataset discovery requires a committed input snapshot.")
        storage = DatasetService(async_sessionmaker(session.bind, expire_on_commit=False))
        raw_candidates = []
        for adapter in self.adapters:
            try:
                raw_candidates.extend(await adapter.search(queries, requirements, countries=countries))
            except Exception as exc:
                logger.warning("Dataset discovery adapter failed (%s)", type(exc).__name__)
        evaluations = await storage._cpu(self.evaluator.evaluate_candidates, raw_candidates, idea, requirements, queries)
        candidates: list[DatasetCandidates] = []
        datasets: list[DatasetSources] = []
        versions: list[DatasetVersions] = []
        try:
            for evaluation in evaluations:
                candidate = evaluation.candidate
                attributes = {attribute.key for attribute in DatasetCandidates.__mapper__.column_attrs}
                values = {name: getattr(candidate, name) for name in DatasetCandidateData.model_fields if name in attributes}
                row = DatasetCandidates(
                    id=f"cand_{uuid.uuid4().hex[:16]}", study_id=study_id, user_id=user_id, run_id=run_id,
                    **values, relevance_score=evaluation.relevance_score, quality_score=evaluation.quality_score,
                    selection_status=evaluation.selection_status, selection_reason=evaluation.selection_reason,
                    evaluation_details={**evaluation.evaluation_details, "is_sample": candidate.is_sample,
                                        "tags": candidate.tags, "modified_at": candidate.modified_at},
                )
                metadata_errors = {}
                for column in DatasetCandidates.__table__.columns:
                    value = values.get(column.name)
                    maximum = column.type.length if isinstance(column.type, String) else None
                    if isinstance(value, str) and maximum is not None and len(value) > maximum:
                        metadata_errors[column.name] = {"actual_length": len(value), "max_length": maximum}
                        replacement = "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest() if column.name in {"source", "external_id"} else f"See evaluation_details.raw_metadata.{column.name}"
                        setattr(row, column.name, replacement)
                if metadata_errors:
                    row.selection_status = "import_failed"
                    row.evaluation_details = {**row.evaluation_details, "metadata_errors": metadata_errors,
                                              "raw_metadata": candidate.model_dump(mode="json"), "import_error": "Dataset metadata exceeds storage limits."}
                elif evaluation.is_selected:
                    try:
                        dataset, version = await _prepare_materialized_candidate(
                            storage, study_id=study_id, user_id=user_id, name=candidate.name,
                            description=candidate.description, source=candidate.source, publisher=candidate.publisher,
                            license_text=candidate.license, url=candidate.url, download_url=candidate.download_url,
                            declared_format=candidate.format, raw_data_content=candidate.raw_data_content, http_client=self._http_client,
                        )
                        row.imported_dataset_id, row.selection_status = dataset.id, "imported"
                        row.sample_rows, row.sample_columns = dataset.row_count, dataset.column_count
                        datasets.append(dataset)
                        versions.append(version)
                    except (DatasetDownloadFailed, DatasetParseError) as exc:
                        row.selection_status = "import_failed"
                        row.evaluation_details = {**row.evaluation_details, "import_error": getattr(exc, "detail", str(exc))}
                    except Exception as exc:
                        row.selection_status = "import_failed"
                        row.evaluation_details = {**row.evaluation_details, "import_error": type(exc).__name__}
                candidates.append(row)
            for version in versions:
                await storage.retain_publication(session, version)
            session.add_all(datasets)
            await session.flush()
            session.add_all(versions)
            session.add_all(candidates)
            await session.flush()
            for row in [*datasets, *candidates]:
                session.expunge(row)
            await session.commit()
            return candidates, datasets
        except BaseException:
            await session.rollback()
            await storage._cleanup_uncommitted_versions(versions)
            raise


class ResearchEngineService:
    """Orchestrates autonomous end-to-end research runs across evidence and public datasets."""

    def __init__(
        self,
        search_provider: Optional[SearchProvider] = None,
        vector_engine: Optional[VectorSearchEngine] = None,
        llm_service: Optional[LLMService] = None,
        discovery_engine: Optional[DatasetDiscoveryEngine] = None,
    ) -> None:
        self.search_provider = search_provider or WikipediaResearchProvider()
        self._owned_search_provider = self.search_provider if search_provider is None else None
        self.vector_engine = vector_engine or VectorSearchEngine()
        self.llm_service = llm_service
        configured_discovery = discovery_engine or DatasetDiscoveryEngine()
        self.discovery_engine = _VersionedDiscoveryEngine(configured_discovery) if type(configured_discovery) is DatasetDiscoveryEngine else configured_discovery
        _upload_dir().mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        provider = self._owned_search_provider
        if provider is not None:
            close = getattr(provider, "aclose", None)
            if callable(close):
                await close()
            self._owned_search_provider = None

    async def run_study_research(
        self,
        session: AsyncSession,
        study: Studies,
        user_id: Optional[str] = None,
        *, job: JobContext | None = None, run_id: str | None = None,
    ) -> ResearchRuns:
        """Execute an autonomous research run for a study, generating research plans, evidence, and discovered datasets."""
        study = _input_snapshot(study)
        if user_id is not None and study.user_id != user_id:
            raise ValueError("Research owner does not match the study owner.")
        effective_user_id = user_id or study.user_id or ANONYMOUS_OWNER_ID
        admitted_run_id = run_id
        run_id = run_id or f"run_{uuid.uuid4().hex[:16]}"
        prompt = study.prompt or study.title
        if job is not None:
            if job.lease.owner_id != effective_user_id or job["scope_id"] != study.id:
                raise ValueError("Research job owner does not match its study.")
            await session.commit()
            await job.begin_item("research_run", input_data={
                "study_id": study.id, "prompt": prompt, "target_audience": study.target_audience,
                "pricing_hypothesis": study.pricing_hypothesis,
            })
            session = cast(AsyncSession, FencedSession(session, job))

        step_progress: dict[str, Any] = {
            "understanding_idea": {"status": "in_progress", "label": "Understanding business idea"},
            "building_research_plan": {"status": "pending", "label": "Building research plan"},
            "searching_evidence": {"status": "pending", "label": "Searching evidence sources"},
            "discovering_datasets": {"status": "pending", "label": "Discovering public datasets"},
            "evaluating_datasets": {"status": "pending", "label": "Evaluating dataset quality & relevance"},
            "importing_datasets": {"status": "pending", "label": "Processing & profiling datasets"},
            "extracting_evidence": {"status": "pending", "label": "Synthesizing evidence claims"},
            # Honesty markers for consumers: where each artefact came from and
            # what was NOT produced. Never a substitute for the artefact itself.
            "summary": {
                "study_revision": study.revision,
                "plan_source": None,
                "queries_source": None,
                "evidence_provider": self.search_provider.name,
                "no_live_evidence": None,
                "claims_status": None,
                "served_by": [],
                "error_code": None,
            },
        }
        summary = step_progress["summary"]
        if job is not None:
            summary["job_id"] = job["job_id"]

        if admitted_run_id is None:
            run = ResearchRuns(id=run_id, study_id=study.id, user_id=effective_user_id)
            session.add(run)
        else:
            run = await session.get(ResearchRuns, run_id)
            if run is None or run.user_id != effective_user_id or run.study_id != study.id or run.status != "queued":
                raise ValueError("Research run is not an owned queued admission.")
        run.status = run.current_step = "understanding_idea"
        run.step_progress = step_progress
        run.started_at = datetime.datetime.now(timezone.utc)
        if job is not None:
            await session.flush()
            await job.complete_item("research_run", result_refs={"run_id": run_id}, session=session)
        await session.commit()
        if job is not None:
            job["result_refs"] = {"run_id": run_id}

        try:
            # -------------------------------------------------------------
            # STEP 1: Understand Business Idea & Generate Research Plan
            # -------------------------------------------------------------
            run.current_step = "building_research_plan"
            step_progress["understanding_idea"]["status"] = "completed"
            step_progress["building_research_plan"]["status"] = "in_progress"
            _mark_progress(run, step_progress)
            await session.commit()

            if job is not None:
                await job.begin_item("research_plan", input_data={"run_id": run_id, "prompt": prompt})
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
            summary["plan_source"] = plan_result.source
            _note_served_by(summary, plan_result.served_by)
            step_progress["building_research_plan"]["status"] = "completed"

            # -------------------------------------------------------------
            # STEP 2: Generate Search Queries & Discover Evidence Sources
            # -------------------------------------------------------------
            run.current_step = "searching_evidence"
            step_progress["searching_evidence"]["status"] = "in_progress"
            _mark_progress(run, step_progress)
            if job is not None:
                await session.flush()
                await job.complete_item("research_plan", result_refs={"run_id": run_id, "plan_id": plan_id}, session=session)
            await session.commit()

            if job is not None:
                await job.begin_item("research_evidence", input_data={"run_id": run_id, "prompt": prompt})
            query_set = await generate_research_queries(
                idea=prompt,
                target_audience=study.target_audience,
                pricing_hypothesis=study.pricing_hypothesis,
                llm_service=self.llm_service,
            )
            queries = query_set.queries
            run.queries = queries
            run.query_count = len(queries)
            summary["queries_source"] = query_set.source
            _note_served_by(summary, query_set.served_by)

            discovered_sources = await self.search_provider.search(queries)
            run.source_count = len(discovered_sources)
            summary["no_live_evidence"] = not discovered_sources

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
                    raw_chunks_for_source = [d.content]
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

            source_inputs = [_input_snapshot(source) for source in sources_to_insert]
            chunk_inputs = [_input_snapshot(chunk) for chunk in chunks_to_insert]
            session.add_all(sources_to_insert)
            await session.flush()
            session.add_all(chunks_to_insert)
            step_progress["searching_evidence"]["status"] = "completed"

            # -------------------------------------------------------------
            # STEP 3: Discover, Evaluate & Auto-Import Public Datasets
            # -------------------------------------------------------------
            run.current_step = "discovering_datasets"
            step_progress["discovering_datasets"]["status"] = "in_progress"
            _mark_progress(run, step_progress)
            if job is not None:
                await session.flush()
                await job.complete_item("research_evidence", result_refs={
                    "source_ids": [source.id for source in source_inputs], "chunk_ids": [chunk.id for chunk in chunk_inputs],
                }, session=session)
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
                    countries=plan_result.target_countries,
                )
                run.dataset_candidate_count = len(candidates)
                run.dataset_imported_count = len(imported_ds)
                summary["target_countries"] = plan_result.target_countries
                summary["no_datasets_found"] = not candidates
                step_progress["discovering_datasets"]["status"] = "completed"
                step_progress["evaluating_datasets"]["status"] = "completed"
                step_progress["importing_datasets"]["status"] = "completed"
            except SQLAlchemyError:
                raise
            except Exception as ds_err:
                if not session.is_active:
                    raise
                logger.warning("dataset discovery step failed for run %s: %s", run_id, type(ds_err).__name__)
                summary["dataset_discovery_error"] = type(ds_err).__name__
                step_progress["discovering_datasets"]["status"] = "completed_with_warnings"
                step_progress["evaluating_datasets"]["status"] = "completed_with_warnings"
                step_progress["importing_datasets"]["status"] = "completed_with_warnings"

            # -------------------------------------------------------------
            # STEP 4: Extract Empirical Claims
            # -------------------------------------------------------------
            run.current_step = "extracting_evidence"
            step_progress["extracting_evidence"]["status"] = "in_progress"
            _mark_progress(run, step_progress)
            await session.commit()

            if job is not None:
                await job.begin_item("research_claims", input_data={
                    "run_id": run_id, "source_ids": [source.id for source in source_inputs],
                    "chunk_ids": [chunk.id for chunk in chunk_inputs],
                })
            if not sources_to_insert:
                # Nothing was found for these queries: say so. No hypothesis
                # list is written in place of evidence (RULES.md R2).
                claims_data: list[dict[str, Any]] = []
                summary["claims_status"] = "no_evidence"
            else:
                if self.llm_service is None:
                    raise LLMUnavailable("Evidence claim extraction")
                claims_data = await extract_claims_with_llm(
                    idea=prompt,
                    sources=source_inputs,
                    chunks=chunk_inputs,
                    llm_service=self.llm_service,
                )
                summary["claims_status"] = "extracted"
                for cd in claims_data:
                    _note_served_by(summary, cd.get("served_by"))

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
                    confidence=cd.get("confidence", 0.0),
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
            run.completed_at = datetime.datetime.now(timezone.utc)
            projection = await session.execute(update(Studies).where(
                Studies.id == study.id, Studies.user_id == study.user_id, Studies.revision == study.revision,
                Studies.status.notin_(("archived", "completed")),
            ).values(status="in_progress", revision=Studies.revision + 1).returning(Studies.id))
            summary["study_projection_applied"] = projection.scalar_one_or_none() is not None
            _mark_progress(run, step_progress)
            if job is not None:
                await session.flush()
                await job.complete_item("research_claims", result_refs={"run_id": run_id, "claim_ids": [claim.id for claim in claims_to_insert]}, session=session)
            await session.commit()
            await session.refresh(run)
            return run

        except (Exception, asyncio.CancelledError) as exc:
            error_code, message = _safe_error(exc)
            database_failed = isinstance(exc, SQLAlchemyError) or not session.is_active
            failed_step = next(
                (name for name, progress in step_progress.items() if progress.get("status") == "in_progress"),
                "finalizing",
            )
            # Full detail to the server log only; the stored message is user-facing.
            logger.warning(
                "research run %s failed at %s: %s",
                run_id,
                failed_step,
                type(exc).__name__,
                exc_info=not isinstance(exc, ExplicitFailure),
            )
            await session.rollback()
            if isinstance(exc, LeaseLost):
                raise
            run = await session.get(ResearchRuns, run_id)
            if run is None:
                raise
            summary["error_code"] = error_code
            if failed_step in step_progress:
                step_progress[failed_step]["status"] = "failed"
            run.status = "failed"
            run.current_step = "failed"
            run.error_message = message
            _mark_progress(run, step_progress)
            run.completed_at = datetime.datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(run)
            if database_failed or job is not None or isinstance(exc, asyncio.CancelledError):
                raise
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
        # The plan table predates the provenance markers; the run that produced
        # the plan stores the full ResearchPlanResult dump (incl. source/served_by).
        source, fallback_reason, served_by = "unknown", None, None
        if plan.run_id:
            run = await session.get(ResearchRuns, plan.run_id)
            dumped = (run.research_plan if run is not None else None) or {}
            if isinstance(dumped, dict):
                source = dumped.get("source") or source
                fallback_reason = dumped.get("fallback_reason")
                served_by = dumped.get("served_by")
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
            "source": source,
            "served_by": served_by,
            "fallback_reason": fallback_reason,
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
        *, job: JobContext | None = None,
    ) -> DatasetSources:
        """Import a discovered candidate by fetching its published resource.

        Raises ``APIError`` (invalid metadata), ``ValueError`` (unknown candidate),
        ``DatasetDownloadFailed`` (no
        resource URL / network / size / HTTP status) or ``DatasetParseError``
        (not tabular). Nothing is generated in place of the download.
        """
        stmt = select(DatasetCandidates).where(
            DatasetCandidates.id == candidate_id,
            DatasetCandidates.study_id == study_id,
        )
        res = await session.execute(stmt)
        candidate = res.scalar_one_or_none()
        if not candidate:
            raise ValueError("Dataset candidate not found")
        if candidate.user_id != user_id:
            raise ValueError("Dataset candidate owner does not match the caller.")

        if (candidate.evaluation_details or {}).get("metadata_errors"):
            raise APIError(
                422,
                "Cannot import this dataset: candidate metadata exceeds storage limits. "
                "Full candidate metadata is preserved in evaluation_details.raw_metadata; "
                "resolve the metadata errors before importing.",
                error_code="invalid_metadata",
            )

        candidate_input = _input_snapshot(candidate)
        if candidate.imported_dataset_id:
            existing = await session.get(DatasetSources, candidate.imported_dataset_id)
            if existing is not None and existing.user_id == user_id:
                if job is not None:
                    refs = {"dataset_id": existing.id, "candidate_id": candidate_id}
                    await job.complete_item("dataset", result_refs=refs, session=session)
                    job["result_refs"] = refs
                    await session.commit()
                    await session.refresh(existing)
                return existing
        await session.commit()
        imported_ds = await materialize_candidate(
            session=session,
            study_id=study_id,
            user_id=user_id,
            name=candidate_input.name,
            description=candidate_input.description or "",
            source=candidate_input.source,
            publisher=candidate_input.publisher or candidate_input.source,
            license_text=candidate_input.license or "",
            url=candidate_input.url,
            download_url=candidate_input.download_url,
            declared_format=candidate_input.format,
            job=job,
        )
        candidate = await session.scalar(select(DatasetCandidates).where(
            DatasetCandidates.id == candidate_id, DatasetCandidates.study_id == study_id,
            DatasetCandidates.user_id == user_id,
        ).with_for_update().execution_options(populate_existing=True))
        if candidate is None or any(getattr(candidate, name) != getattr(candidate_input, name) for name in (
            "name", "description", "source", "publisher", "license", "url", "download_url", "format", "imported_dataset_id",
        )):
            await session.rollback()
            raise APIError(409, "The dataset candidate changed during import.", error_code="dataset_candidate_changed")
        candidate.imported_dataset_id = imported_ds.id
        candidate.selection_status = "imported"
        candidate.sample_rows = imported_ds.row_count
        candidate.sample_columns = imported_ds.column_count
        if job is not None:
            refs = {"dataset_id": imported_ds.id, "candidate_id": candidate_id}
            await job.complete_item("dataset", result_refs=refs, session=session)
            job["result_refs"] = refs
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
        claims_stmt = (
            select(EvidenceClaims.status, func.count(EvidenceClaims.id))
            .where(EvidenceClaims.study_id == study_id)
            .group_by(EvidenceClaims.status)
        )
        claims_by_status = dict((await session.execute(claims_stmt)).all())

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

        total_claims = sum(claims_by_status.values())
        supported_count = claims_by_status.get("supported", 0)
        inferred_count = claims_by_status.get("inference", 0)
        unsupported_count = claims_by_status.get("unsupported", 0)

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
