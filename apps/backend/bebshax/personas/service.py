"""Service orchestration for synthetic persona generation runs and persistence."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.utils.safe_errors import safe_error_summary
from bebshax.db.models import (
    DatasetSources,
    EvidenceClaims,
    MarketSegments,
    PersonaGenerationRuns,
    Personas,
    SegmentationRuns,
    Studies,
    _utcnow,
)
from bebshax.llm.service import LLMService
from bebshax.personas.generator import generate_personas_for_study

logger = logging.getLogger(__name__)

# Generator only consumes up to 6 claims; fetch no more to avoid full-table scans.
_CLAIM_FETCH_LIMIT = 6

_ACTIVE_RUN_STATES = (
    "pending", "loading_segments", "preparing_context", "generating_personas",
    "validating_personas", "saving_personas",
)
# A run that has shown no progress for this long is a crashed process, not an
# active one; without this cutoff a single interrupted run locked the study
# out of persona generation until someone deleted the row by hand.
STALE_RUN_AFTER = timedelta(minutes=30)


def _run_age(run: PersonaGenerationRuns, now: datetime) -> timedelta:
    started = run.started_at or run.created_at
    if started is None:
        return timedelta(0)
    if started.tzinfo is None:  # sqlite hands back naive UTC
        started = started.replace(tzinfo=timezone.utc)
    return now - started


class PersonaGenerationService:
    def __init__(self, session: AsyncSession, llm_service: Optional[LLMService] = None) -> None:
        self.session = session
        self.llm_service = llm_service

    async def list_runs(self, study_id: str, user_id: Optional[str] = None) -> list[PersonaGenerationRuns]:
        """List historical persona generation runs for a study."""
        stmt = (
            select(PersonaGenerationRuns)
            .where(PersonaGenerationRuns.study_id == study_id)
            .order_by(PersonaGenerationRuns.created_at.desc())
        )
        if user_id:
            stmt = stmt.where(PersonaGenerationRuns.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_run(self, study_id: str, run_id: str, user_id: Optional[str] = None) -> Optional[PersonaGenerationRuns]:
        """Get a single persona generation run."""
        stmt = select(PersonaGenerationRuns).where(
            PersonaGenerationRuns.id == run_id,
            PersonaGenerationRuns.study_id == study_id,
        )
        if user_id:
            stmt = stmt.where(PersonaGenerationRuns.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_run(self, study_id: str, run_id: str, user_id: Optional[str] = None) -> bool:
        """Delete a persona generation run and its generated personas."""
        run = await self.get_run(study_id, run_id, user_id)
        if not run:
            return False

        # Delete associated personas
        await self.session.execute(
            delete(Personas).where(
                Personas.generation_run_id == run_id,
                Personas.study_id == study_id,
            )
        )
        await self.session.delete(run)
        await self.session.commit()
        return True

    async def create_generation_run(
        self,
        study_id: str,
        user_id: Optional[str] = None,
        segmentation_run_id: Optional[str] = None,
        personas_per_segment: Optional[int] = None,
        target_count: Optional[int] = None,
        distribution_strategy: str = "population_weighted",
    ) -> tuple[PersonaGenerationRuns, list[Personas]]:
        """Orchestrate and persist a complete synthetic persona generation run."""
        # 1. Fetch study
        study = await self.session.get(Studies, study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found.")

        # 2. Check for active run — stale ones (no progress for STALE_RUN_AFTER)
        # are marked failed and no longer block a new run.
        active_stmt = select(PersonaGenerationRuns).where(
            PersonaGenerationRuns.study_id == study_id,
            PersonaGenerationRuns.status.in_(_ACTIVE_RUN_STATES),
        )
        if user_id:
            active_stmt = active_stmt.where(PersonaGenerationRuns.user_id == user_id)
        now = _utcnow()
        stale_found = False
        for active_run in (await self.session.execute(active_stmt)).scalars().all():
            if _run_age(active_run, now) < STALE_RUN_AFTER:
                raise ValueError(f"A persona generation run is already in progress ({active_run.id}).")
            logger.warning(
                "persona generation run %s stuck in %r for over %s — marking failed",
                active_run.id, active_run.status, STALE_RUN_AFTER,
            )
            active_run.status = "failed"
            active_run.error_message = "StaleRun: no progress for 30 minutes (process interrupted)"
            active_run.completed_at = now
            stale_found = True
        if stale_found:
            await self.session.commit()

        # 3. Load segments
        seg_stmt = select(MarketSegments).where(MarketSegments.study_id == study_id)
        if segmentation_run_id:
            seg_stmt = seg_stmt.where(MarketSegments.segmentation_run_id == segmentation_run_id)
        if user_id:
            seg_stmt = seg_stmt.where(MarketSegments.user_id == user_id)
        seg_stmt = seg_stmt.order_by(MarketSegments.created_at.desc())
        segments = list((await self.session.execute(seg_stmt)).scalars().all())

        if not segments:
            raise ValueError("No market segments found for this study. Please run market segmentation first.")

        # If no segmentation_run_id provided, take the run id of the latest segments
        target_seg_run_id = segmentation_run_id or segments[0].segmentation_run_id

        # Calculate final target count
        final_target_count = target_count or (len(segments) * (personas_per_segment or 2))

        # 4. Load datasets and claims snapshots
        ds_stmt = select(DatasetSources).where(DatasetSources.study_id == study_id)
        datasets = list((await self.session.execute(ds_stmt)).scalars().all())
        dataset_snapshots = [
            {
                "dataset_id": d.id,
                "name": d.name,
                "content_hash": d.content_hash,
                "row_count": d.row_count,
                "is_sample": bool((d.schema_metadata or {}).get("is_sample", False)),
            }
            for d in datasets
        ]

        claim_stmt = (
            select(EvidenceClaims)
            .where(EvidenceClaims.study_id == study_id)
            .order_by(EvidenceClaims.confidence.desc(), EvidenceClaims.created_at.desc())
            .limit(_CLAIM_FETCH_LIMIT)
        )
        claims = list((await self.session.execute(claim_stmt)).scalars().all())
        # claim_count is a provenance fact about the study, not about how many
        # claims we chose to feed the model — count the real total separately.
        total_claim_count = (
            await self.session.execute(
                select(func.count())
                .select_from(EvidenceClaims)
                .where(EvidenceClaims.study_id == study_id)
            )
        ).scalar_one()
        evidence_snapshot = {
            "claim_count": int(total_claim_count or 0),
            "claims_used_count": len(claims),
            "top_claims": [
                {"id": c.id, "claim_text": c.claim_text, "category": c.category, "confidence": c.confidence}
                for c in claims[:5]
            ],
        }

        # 5. Create Run Record
        run_id = f"pgen_{uuid.uuid4().hex[:12]}"
        run = PersonaGenerationRuns(
            id=run_id,
            study_id=study_id,
            user_id=user_id,
            segmentation_run_id=target_seg_run_id,
            status="loading_segments",
            configuration={
                "personas_per_segment": personas_per_segment,
                "target_count": final_target_count,
                "distribution_strategy": distribution_strategy,
            },
            target_count=final_target_count,
            generated_count=0,
            valid_count=0,
            warning_count=0,
            dataset_versions=dataset_snapshots,
            evidence_snapshot=evidence_snapshot,
            started_at=_utcnow(),
        )
        self.session.add(run)
        await self.session.commit()

        # Step 6: Generate Personas
        try:
            run.status = "generating_personas"
            await self.session.commit()

            drafts = await generate_personas_for_study(
                study=study,
                segments=segments,
                target_count=final_target_count,
                distribution_strategy=distribution_strategy,
                datasets=datasets,
                evidence_claims=claims,
                llm_service=self.llm_service,
            )

            run.status = "saving_personas"
            await self.session.commit()

            persisted_personas: list[Personas] = []
            valid_count = 0
            warning_count = 0

            # Match drafts to segments
            seg_map = {s.name: s.id for s in segments}
            seg_id_fallback = segments[0].id

            for idx, draft in enumerate(drafts):
                # find matching segment id
                matched_sid = seg_id_fallback
                for s in segments:
                    if s.name in draft.archetype or s.name in draft.bio:
                        matched_sid = s.id
                        break

                persona_id = f"per_{uuid.uuid4().hex[:12]}"
                p_entity = Personas(
                    id=persona_id,
                    study_id=study_id,
                    user_id=user_id,
                    owner_id=user_id or "usr_system_holder",
                    segment_id=matched_sid,
                    generation_run_id=run_id,
                    name=draft.name,
                    status=draft.status,
                    version=1,
                    # The draft carries its true origin (provenance-derived
                    # provider/model or the template label) — never a
                    # fabricated constant.
                    generation_model=draft.generation_model or "deterministic-empirical-generator",
                    archetype=draft.archetype,
                    tagline=draft.tagline,
                    country_code=draft.country_code,
                    personality=draft.personality,
                    detailed_attributes=draft.detailed_attributes,
                    demographics=draft.demographics,
                    bio=draft.bio,
                    quote=draft.quote,
                    goals=draft.goals,
                    needs=draft.needs,
                    pain_points=draft.pain_points,
                    behaviors=draft.behaviors,
                    preferences=draft.preferences,
                    motivations=draft.motivations,
                    objections=draft.objections,
                    commercial_profile=draft.commercial_profile,
                    technology_profile=draft.technology_profile,
                    evidence_citations=draft.evidence_citations,
                    dataset_refs=draft.dataset_refs,
                    grounding_score=draft.grounding_score,
                    confidence=draft.confidence,
                    validation_warnings=draft.validation_warnings,
                    is_synthetic=True,
                    created_at=_utcnow(),
                    updated_at=_utcnow(),
                )
                self.session.add(p_entity)
                persisted_personas.append(p_entity)

                if draft.status == "ready":
                    valid_count += 1
                else:
                    warning_count += 1

            # Update study & run record
            run.status = "completed"
            run.generated_count = len(persisted_personas)
            run.valid_count = valid_count
            run.warning_count = warning_count
            run.completed_at = _utcnow()

            # Update study step & count
            study.persona_count = len(persisted_personas)
            study.step = max(study.step, 3)

            await self.session.commit()
            return run, persisted_personas

        except Exception as exc:
            run.status = "failed"
            # Class name + correlation code only: the raw message can carry
            # prompt fragments or provider error bodies (served by the API).
            run.error_message = safe_error_summary(exc)
            run.completed_at = _utcnow()
            logger.error(
                "persona generation run %s failed: %s", run_id, run.error_message, exc_info=True
            )
            await self.session.commit()
            raise exc

    async def list_personas(
        self,
        study_id: str,
        user_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        status: Optional[str] = None,
        generation_run_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Personas]:
        """List study personas with optional filters and pagination."""
        stmt = (
            select(Personas)
            .where(Personas.study_id == study_id)
            .order_by(Personas.created_at.desc())
        )
        if user_id:
            stmt = stmt.where(Personas.user_id == user_id)
        if segment_id:
            stmt = stmt.where(Personas.segment_id == segment_id)
        if status:
            stmt = stmt.where(Personas.status == status)
        if generation_run_id:
            stmt = stmt.where(Personas.generation_run_id == generation_run_id)
        if search:
            like_term = f"%{search.strip()}%"
            stmt = stmt.where(
                (Personas.name.ilike(like_term))
                | (Personas.archetype.ilike(like_term))
                | (Personas.bio.ilike(like_term))
            )

        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_persona(
        self, study_id: str, persona_id: str, user_id: Optional[str] = None
    ) -> Optional[Personas]:
        """Get a single persona by ID with ownership verification."""
        stmt = select(Personas).where(
            Personas.id == persona_id,
            Personas.study_id == study_id,
        )
        if user_id:
            stmt = stmt.where(Personas.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def regenerate_persona(
        self, study_id: str, persona_id: str, user_id: Optional[str] = None
    ) -> Personas:
        """Regenerate a single persona to create a new version while preserving grounding."""
        persona = await self.get_persona(study_id, persona_id, user_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found.")

        # Load segment
        segment = None
        if persona.segment_id:
            segment = await self.session.get(MarketSegments, persona.segment_id)

        # Load claims
        claim_stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
        claims = list((await self.session.execute(claim_stmt)).scalars().all())

        study = await self.session.get(Studies, study_id)

        # Generate fresh draft
        if segment:
            drafts = await generate_personas_for_study(
                study=study,
                segments=[segment],
                target_count=1,
                distribution_strategy="equal",
                evidence_claims=claims,
                llm_service=self.llm_service,
            )
            if drafts:
                draft = drafts[0]
                persona.version += 1
                persona.name = draft.name
                persona.archetype = draft.archetype
                persona.tagline = draft.tagline
                persona.country_code = draft.country_code
                persona.personality = draft.personality
                persona.detailed_attributes = draft.detailed_attributes
                persona.demographics = draft.demographics
                persona.bio = draft.bio
                persona.quote = draft.quote
                persona.goals = draft.goals
                persona.needs = draft.needs
                persona.pain_points = draft.pain_points
                persona.behaviors = draft.behaviors
                persona.preferences = draft.preferences
                persona.motivations = draft.motivations
                persona.objections = draft.objections
                persona.commercial_profile = draft.commercial_profile
                persona.technology_profile = draft.technology_profile
                persona.evidence_citations = draft.evidence_citations
                persona.dataset_refs = draft.dataset_refs
                persona.grounding_score = draft.grounding_score
                persona.confidence = draft.confidence
                persona.status = draft.status
                persona.validation_warnings = draft.validation_warnings
                persona.updated_at = _utcnow()
                await self.session.commit()

        return persona
