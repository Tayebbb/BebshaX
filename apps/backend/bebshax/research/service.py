"""Research engine service orchestrating end-to-end research runs and evidence analytics.

Coordinates query generation, source collection, document chunking, pgvector embedding,
claim extraction, and empirical evidence summaries.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import uuid
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import (
    EvidenceChunks,
    EvidenceClaims,
    EvidenceSources,
    ResearchRuns,
    Studies,
)
from bebshax.llm.adapters.embeddings import CANONICAL_DIM
from bebshax.llm.service import LLMService
from bebshax.research.chunker import chunk_document
from bebshax.research.claim_extractor import (
    extract_claims_with_llm,
    extract_deterministic_claims,
)
from bebshax.research.query_generator import generate_research_queries
from bebshax.research.search_provider import (
    CuratedResearchProvider,
    SearchProvider,
)
from bebshax.research.vector_search import VectorSearchEngine


class ResearchEngineService:
    def __init__(
        self,
        search_provider: Optional[SearchProvider] = None,
        vector_engine: Optional[VectorSearchEngine] = None,
        llm_service: Optional[LLMService] = None,
    ) -> None:
        self.search_provider = search_provider or CuratedResearchProvider()
        self.vector_engine = vector_engine or VectorSearchEngine()
        self.llm_service = llm_service

    async def run_study_research(
        self,
        session: AsyncSession,
        study: Studies,
        user_id: Optional[str] = None,
    ) -> ResearchRuns:
        """Execute a complete research run for a study and persist sources, chunks, and claims."""
        effective_user_id = user_id or study.user_id or "usr_default"
        run_id = f"run_{uuid.uuid4().hex[:16]}"

        run = ResearchRuns(
            id=run_id,
            study_id=study.id,
            user_id=effective_user_id,
            status="generating_queries",
            started_at=datetime.datetime.now(timezone.utc),
        )
        session.add(run)
        await session.commit()

        try:
            # 1. Generate queries
            prompt = study.prompt or study.title
            queries = await generate_research_queries(
                idea=prompt,
                target_audience=study.target_audience,
                pricing_hypothesis=study.pricing_hypothesis,
                llm_service=self.llm_service,
            )
            run.queries = queries
            run.query_count = len(queries)
            run.status = "collecting_sources"
            await session.commit()

            # 2. Search permitted sources
            discovered = await self.search_provider.search(queries)
            run.source_count = len(discovered)
            run.status = "processing_chunks"
            await session.commit()

            # 3. Clean, chunk, and embed sources
            sources_to_insert: list[EvidenceSources] = []
            chunks_to_insert: list[EvidenceChunks] = []

            for d in discovered:
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

                # Chunk document
                raw_chunks = chunk_document(d.content, chunk_size=400, chunk_overlap=40)
                if not raw_chunks:
                    raw_chunks = [d.content[:400]]

                embeddings = await self.vector_engine.embed_texts(raw_chunks)

                for idx, (chunk_text, emb) in enumerate(zip(raw_chunks, embeddings)):
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
            run.status = "extracting_evidence"
            await session.commit()

            # 4. Extract claims and classify evidence status
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
            run.status = "completed"
            run.completed_at = datetime.datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(run)
            return run

        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(run)
            return run

    async def get_evidence_summary(
        self,
        session: AsyncSession,
        study_id: str,
    ) -> dict[str, Any]:
        """Calculate evidence coverage and classification distribution from database."""
        # Get claims
        claims_stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
        claims_result = await session.execute(claims_stmt)
        claims = list(claims_result.scalars().all())

        # Get sources count
        sources_count_stmt = select(func.count(EvidenceSources.id)).where(EvidenceSources.study_id == study_id)
        sources_count_result = await session.execute(sources_count_stmt)
        source_count = sources_count_result.scalar() or 0

        # Get latest run
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
            "evidence_coverage": evidence_coverage,
            "supported_pct": supported_pct,
            "inferred_pct": inferred_pct,
            "unsupported_pct": unsupported_pct,
            "supported_count": supported_count,
            "inferred_count": inferred_count,
            "unsupported_count": unsupported_count,
            "total_claims": total_claims,
            "total_sources": source_count,
            "latest_run": {
                "id": latest_run.id,
                "status": latest_run.status,
                "query_count": latest_run.query_count,
                "source_count": latest_run.source_count,
                "claim_count": latest_run.claim_count,
                "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
                "error_message": latest_run.error_message,
            } if latest_run else None,
        }
