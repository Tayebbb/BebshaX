"""Service orchestration for synthetic persona generation runs and persistence."""

from __future__ import annotations

import logging
import hashlib
import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from bebshax.api.errors import APIError
from bebshax.datasets.orm import DatasetVersions
from bebshax.jobs.orm import DurableJobs
from bebshax.jobs.runtime import FencedSession, JobContext
from bebshax.jobs.store import LeaseLost
from bebshax.utils.safe_errors import safe_error_summary
from bebshax.db.models import (
    Businesses,
    DatasetSources,
    EvidenceClaims,
    MarketSegments,
    PersonaGenerationRuns,
    Personas,
    Studies,
    _utcnow,
)
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm.service import LLMService
from bebshax.memory.orm import MemoryItems
from bebshax.persona.orm import PersonaAttributes, PersonaDetails, PersonaEvidence
from bebshax.personas.generator import generate_personas_for_study
from bebshax.personas.ml_adapter import MLPersonaAdapter
from bebshax.personas.orm import PersonaSourceSelections, PersonaVersions
from bebshax.personas.source_ledger import release_source_selections, source_exclusions, synchronize_persona_source
from bebshax.tenancy import PUBLIC_OWNER_IDS, allowed_owner_ids

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
WORKFLOW_PERSONA_FIELDS = (
    "description", "age", "occupation", "location", "income_range", "education",
    "role_id", "role_title", "initials", "badges", "attributes", "grounding_ratio",
    "grounding_basis", "evidence_claim_count", "consistency_score",
)


async def capture_persona_input_versions(session: AsyncSession, study_id: str) -> dict[str, Any]:
    study = await session.get(Studies, study_id, populate_existing=True)
    if study is None:
        raise APIError(404, "Study not found.", error_code="not_found")

    def fingerprint(row: Any) -> str:
        values = {attribute.key: getattr(row, attribute.key) for attribute in row.__mapper__.column_attrs}
        return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    versions: dict[str, Any] = {"study_revision": study.revision, "study_hash": fingerprint(study)}
    for model in (MarketSegments, DatasetSources, EvidenceClaims, Personas, PersonaSourceSelections):
        statement = select(model).where(model.study_id == study_id)
        if model is Personas:
            statement = statement.where(Personas.status != "archived")
        if model is PersonaSourceSelections:
            statement = statement.where(PersonaSourceSelections.released_at.is_(None))
        rows = list(await session.scalars(statement.order_by(model.id).execution_options(populate_existing=True)))
        versions[model.__tablename__] = [{"id": row.id, "hash": fingerprint(row)} for row in rows]
    published = list(await session.scalars(select(DatasetVersions).join(
        DatasetSources, (DatasetVersions.dataset_id == DatasetSources.id)
        & (DatasetVersions.file_path == DatasetSources.file_path)
        & (DatasetVersions.content_hash == DatasetSources.content_hash),
    ).where(DatasetSources.study_id == study_id).order_by(DatasetVersions.id)))
    versions["dataset_versions"] = [{"id": row.id, "version": row.version, "hash": fingerprint(row)} for row in published]
    return versions


async def record_persona_version(
    session: AsyncSession, persona: Personas, *,
    legacy_profile: dict[str, Any] | None = None,
    capture_kind: Literal["generated", "observed_current"] = "generated",
) -> PersonaVersions:
    """Append the available version in the caller's transaction; never invent older history."""
    await session.flush()
    if not persona.owner_id or persona.version < 1:
        raise ValueError("A persona version requires an owner and a positive version.")
    existing = await session.get(PersonaVersions, (persona.id, persona.version))
    if existing is not None:
        if existing.owner_id != persona.owner_id:
            raise ValueError("Persona version owner is immutable.")
        immutable_fields = (
            "study_id", "business_id", "generation_run_id", "segment_id",
            "dataset_persona_run_id", "dataset_version_id", "dataset_segment_key",
        )
        old_source = (existing.snapshot.get("detailed_attributes") or {}).get("ml_provenance")
        new_source = (persona.detailed_attributes or {}).get("ml_provenance")
        if old_source != new_source or any(
            existing.snapshot.get(field) != getattr(persona, field) for field in immutable_fields
        ):
            raise ValueError("Persona version source and parent lineage are immutable.")
        await synchronize_persona_source(session, persona, existing)
        return existing
    snapshot = {
        column.name: (
            value.isoformat() if isinstance(value := getattr(persona, column.name), datetime) else deepcopy(value)
        )
        for column in Personas.__table__.columns
    }
    version = PersonaVersions(
        persona_id=persona.id, version=persona.version, owner_id=persona.owner_id,
        study_id=persona.study_id, snapshot=snapshot, legacy_profile=deepcopy(legacy_profile),
        capture_kind=capture_kind,
    )
    session.add(version)
    await session.flush()
    await synchronize_persona_source(session, persona, version)
    return version


async def list_persona_versions(
    session: AsyncSession, persona_id: str, *, owner_id: str,
) -> list[PersonaVersions]:
    return list((await session.scalars(
        select(PersonaVersions).where(
            PersonaVersions.persona_id == persona_id, PersonaVersions.owner_id == owner_id,
        ).order_by(PersonaVersions.version)
    )).all())


async def get_persona_version(
    session: AsyncSession, persona_id: str, version: int, *, owner_id: str,
) -> PersonaVersions | None:
    return (await session.scalars(select(PersonaVersions).where(
        PersonaVersions.persona_id == persona_id, PersonaVersions.version == version,
        PersonaVersions.owner_id == owner_id,
    ))).one_or_none()


def serialize_persona(persona: Personas, segment_name: str | None = None) -> dict[str, Any]:
    """Canonical public representation shared by persona and study endpoints."""
    detailed = persona.detailed_attributes or {}
    commercial = persona.commercial_profile or {}
    result = {
        column.name: getattr(persona, column.name)
        for column in Personas.__table__.columns
        if column.name not in {"owner_id", "business_id"}
    }
    for field in (
        "goals", "needs", "pain_points", "behaviors", "preferences", "motivations",
        "objections", "evidence_citations", "dataset_refs", "validation_warnings",
    ):
        result[field] = result[field] or []
    for field in ("personality", "demographics", "technology_profile"):
        result[field] = result[field] or {}
    result.update(
        segment_name=segment_name,
        data_source=persona.data_source or "live",
        detailed_attributes=detailed,
        commercial_profile=commercial,
        domain_attributes=detailed.get("domain_attributes", {}),
        constraints=detailed.get("constraints") or commercial.get("constraints", {}),
    )
    for field in ("created_at", "updated_at"):
        value = result[field]
        result[field] = value.isoformat() if value else None
    projection = detailed.get("workflow_projection")
    if isinstance(projection, dict):
        result.update({field: deepcopy(projection[field]) for field in WORKFLOW_PERSONA_FIELDS if field in projection})
    return result


async def canonical_study_persona_states(
    session: AsyncSession, studies: list[Studies],
) -> dict[str, dict[str, Any]]:
    """Build active snapshots in one query, excluding inconsistent cross-tenant rows."""
    states: dict[str, dict[str, Any]] = {
        study.id: {"persona_count": 0, "persona_ids": [], "personas_data": []}
        for study in studies
    }
    if not states:
        return states
    statement = (
        select(Personas)
        .join(Studies, Studies.id == Personas.study_id)
        .where(
            Studies.id.in_(states), Personas.status != "archived",
            Personas.owner_id == func.coalesce(Studies.user_id, "usr_system_holder"),
        )
        .order_by(Personas.created_at, Personas.id)
    )
    for persona in (await session.scalars(statement)).all():
        if persona.study_id is None:
            continue
        state = states[persona.study_id]
        state["persona_ids"].append(persona.id)
        state["personas_data"].append(serialize_persona(persona))
        state["persona_count"] += 1
    return states


def _run_age(run: PersonaGenerationRuns, now: datetime) -> timedelta:
    started = run.started_at or run.created_at
    if started is None:
        return timedelta(0)
    if started.tzinfo is None:  # sqlite hands back naive UTC
        started = started.replace(tzinfo=timezone.utc)
    return now - started


async def lock_persona_parent(
    session: AsyncSession, *, owner_id: str, study_id: str | None = None,
    business_id: str | None = None, dataset_id: str | None = None,
    allow_shared_business: bool = False,
) -> Studies | Businesses | DatasetSources:
    """Lock one owned parent until commit/rollback; call before exclusions and writes.

    PostgreSQL serializes cooperating writers. SQLite ignores FOR UPDATE.
    """
    parents = [
        (Studies, study_id, Studies.user_id),
        (Businesses, business_id, Businesses.owner_id),
        (DatasetSources, dataset_id, DatasetSources.user_id),
    ]
    selected = [parent for parent in parents if parent[1] is not None]
    if len(selected) != 1:
        raise ValueError("Exactly one persona parent must be specified.")
    parent_model, parent_id, owner_column = selected[0]
    if allow_shared_business and business_id is None:
        raise ValueError("Shared parent access applies only to businesses.")
    owner_scope = func.coalesce(owner_column, "usr_system_holder") == owner_id
    if allow_shared_business:
        owner_scope = owner_column.in_(allowed_owner_ids(owner_id))
    statement = (
        select(parent_model)
        .where(
            parent_model.id == parent_id,
            owner_scope,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    parent = (await session.execute(statement)).scalar_one_or_none()
    if parent is None:
        raise ValueError("Persona parent not found for this owner.")
    return parent


async def delete_persona_artifacts(
    session: AsyncSession, *, owner_id: str, scope: ColumnElement[bool],
) -> set[str]:
    """Delete owned personas and their dependents in the caller's parent-locked transaction."""
    persona_ids = set((await session.scalars(
        select(Personas.id).where(scope, Personas.owner_id == owner_id).with_for_update()
    )).all())
    if not persona_ids:
        return persona_ids
    conversation_ids = select(Conversations.id).where(
        Conversations.persona_id.in_(persona_ids),
        Conversations.user_id.is_(None) | (Conversations.user_id == owner_id),
    )
    await session.execute(delete(ConversationTurns).where(
        ConversationTurns.conversation_id.in_(conversation_ids),
    ))
    await session.execute(delete(InterviewInsights).where(
        InterviewInsights.interview_id.in_(conversation_ids)
        | InterviewInsights.persona_id.in_(persona_ids),
        InterviewInsights.user_id.is_(None) | (InterviewInsights.user_id == owner_id),
    ))
    await session.execute(delete(MemoryItems).where(MemoryItems.persona_id.in_(persona_ids)))
    await session.execute(delete(Conversations).where(Conversations.id.in_(conversation_ids)))
    for model in (PersonaAttributes, PersonaEvidence, PersonaDetails, PersonaSourceSelections, PersonaVersions):
        await session.execute(delete(model).where(model.persona_id.in_(persona_ids)))
    await session.execute(delete(Personas).where(Personas.id.in_(persona_ids)))
    return persona_ids


async def refresh_study_persona_state(
    session: AsyncSession, *, study: Studies, owner_id: str, removed_ids: set[str],
) -> None:
    """Refresh every derived field inside the caller's parent-locked transaction."""
    if (study.user_id or "usr_system_holder") != owner_id:
        raise ValueError("Study not found for this owner.")
    await session.flush()
    if owner_id not in PUBLIC_OWNER_IDS:
        archived_ids = set((await session.scalars(select(Personas.id).where(
            Personas.study_id == study.id, Personas.owner_id == owner_id, Personas.status == "archived",
        ))).all())
        await release_source_selections(
            session, owner_id=owner_id, study_id=study.id, persona_ids=archived_ids | removed_ids,
        )
        dataset_ids = (await session.scalars(select(PersonaSourceSelections.dataset_id).join(
            DatasetSources, DatasetSources.id == PersonaSourceSelections.dataset_id,
        ).where(
            PersonaSourceSelections.owner_id == owner_id,
            PersonaSourceSelections.scope_owner_id == DatasetSources.user_id,
            PersonaSourceSelections.persona_id.in_(archived_ids | removed_ids),
            PersonaSourceSelections.released_at.is_(None),
            DatasetSources.study_id.is_(None) | (DatasetSources.study_id == study.id),
        ).distinct())).all()
        for dataset_id in dataset_ids:
            await release_source_selections(
                session, owner_id=owner_id, dataset_id=dataset_id, persona_ids=archived_ids | removed_ids,
            )
    state = (await canonical_study_persona_states(session, [study]))[study.id]
    study.persona_count = state["persona_count"]
    study.persona_ids = state["persona_ids"]
    study.personas_data = state["personas_data"]


async def active_source_exclusions(
    session: AsyncSession, *, owner_id: str, scope: ColumnElement[bool],
    study_id: str | None = None, business_id: str | None = None, dataset_id: str | None = None,
) -> tuple[set[str], set[str]]:
    exclude_ids: set[str] = set()
    exclude_names: set[str] = set()
    existing_stmt = select(Personas.detailed_attributes, Personas.name).where(
        scope, Personas.owner_id == owner_id, Personas.status != "archived",
    )
    for detailed, name in (await session.execute(existing_stmt)).all():
        provenance = (detailed or {}).get("ml_provenance", {})
        if isinstance(provenance, dict) and provenance.get("record_id"):
            exclude_ids.add(provenance["record_id"])
        if name:
            exclude_names.add(name)
    if any(parent is not None for parent in (study_id, business_id, dataset_id)):
        source_ids, source_names = await source_exclusions(
            session, owner_id=owner_id, study_id=study_id, business_id=business_id, dataset_id=dataset_id,
        )
        exclude_ids.update(source_ids)
        exclude_names.update(source_names)
    return exclude_ids, exclude_names


class PersonaGenerationService:
    def __init__(
        self, session: AsyncSession, llm_service: Optional[LLMService] = None,
        *, ml_generator: MLPersonaAdapter | None = None,
    ) -> None:
        self.session = session
        self.llm_service = llm_service
        self.ml_generator = ml_generator
        if self.ml_generator is None and llm_service is None:
            self.ml_generator = MLPersonaAdapter.from_settings()

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

        owner_id = run.user_id or user_id or "usr_system_holder"
        try:
            study = cast(Studies, await lock_persona_parent(
                self.session, owner_id=owner_id, study_id=study_id,
            ))
            removed_ids = await delete_persona_artifacts(
                self.session, owner_id=owner_id,
                scope=(Personas.generation_run_id == run_id) & (Personas.study_id == study_id),
            )
            await self.session.delete(run)
            await refresh_study_persona_state(
                self.session, study=study, owner_id=owner_id, removed_ids=removed_ids,
            )
            await self.session.commit()
            return True
        except IntegrityError as exc:
            await self.session.rollback()
            raise APIError(
                409, "The persona run still has conflicting references.", error_code="data_integrity",
            ) from exc
        except BaseException:
            await self.session.rollback()
            raise

    async def create_generation_run(
        self,
        study_id: str,
        user_id: Optional[str] = None,
        segmentation_run_id: Optional[str] = None,
        personas_per_segment: Optional[int] = None,
        target_count: Optional[int] = None,
        distribution_strategy: str = "population_weighted",
        existing_run_id: Optional[str] = None,
        *, job: JobContext | None = None, expected_input_versions: dict[str, Any] | None = None,
    ) -> tuple[PersonaGenerationRuns, list[Personas]]:
        """Orchestrate and persist a complete synthetic persona generation run."""
        original_session = self.session
        try:
            if job is not None:
                if job.lease.owner_id != user_id or job["scope_id"] != study_id:
                    raise ValueError("Persona job does not match its owner and study.")
                if expected_input_versions is not None and await capture_persona_input_versions(self.session, study_id) != expected_input_versions:
                    raise APIError(409, "Persona inputs changed after admission.", error_code="persona_input_changed")
                await self.session.rollback()
                await job.begin_item("persona_generation", input_data={"study_id": study_id, "input_versions": expected_input_versions})
                self.session = cast(AsyncSession, FencedSession(self.session, job))
            return await self._create_generation_run(
                study_id, user_id, segmentation_run_id, personas_per_segment,
                target_count, distribution_strategy, existing_run_id, job, expected_input_versions,
            )
        except IntegrityError as exc:
            await self.session.rollback()
            raise APIError(
                409, "Persona generation conflicts with existing data.", error_code="data_integrity",
            ) from exc
        except BaseException:
            await self.session.rollback()
            raise
        finally:
            self.session = original_session

    async def _create_generation_run(
        self, study_id: str, user_id: Optional[str], segmentation_run_id: Optional[str],
        personas_per_segment: Optional[int], target_count: Optional[int],
        distribution_strategy: str, existing_run_id: Optional[str],
        job: JobContext | None = None, expected_input_versions: dict[str, Any] | None = None,
    ) -> tuple[PersonaGenerationRuns, list[Personas]]:
        owner_id = user_id or "usr_system_holder"
        study = cast(Studies, await lock_persona_parent(
            self.session, owner_id=owner_id, study_id=study_id,
        ))
        if expected_input_versions is not None and await capture_persona_input_versions(self.session, study_id) != expected_input_versions:
            raise APIError(409, "Persona inputs changed after admission.", error_code="persona_input_changed")
        run = None
        if existing_run_id is not None:
            run = await self.get_run(study_id, existing_run_id, user_id)
            if run is None or (run.user_id or "usr_system_holder") != owner_id:
                raise ValueError("Reserved persona generation run not found.")
            if run.status != "pending":
                raise ValueError(f"A persona generation run is already in progress ({run.id}).")

        # 2. Check for active run — stale ones (no progress for STALE_RUN_AFTER)
        # are marked failed and no longer block a new run.
        active_stmt = select(PersonaGenerationRuns).where(
            PersonaGenerationRuns.study_id == study_id,
            func.coalesce(PersonaGenerationRuns.user_id, "usr_system_holder") == owner_id,
            PersonaGenerationRuns.status.in_(_ACTIVE_RUN_STATES),
        )
        now = _utcnow()
        for active_run in (await self.session.execute(active_stmt)).scalars().all():
            if active_run.id == existing_run_id:
                continue
            if _run_age(active_run, now) < STALE_RUN_AFTER:
                raise ValueError(f"A persona generation run is already in progress ({active_run.id}).")
            logger.warning(
                "persona generation run %s stuck in %r for over %s — marking failed",
                active_run.id, active_run.status, STALE_RUN_AFTER,
            )
            active_run.status = "failed"
            active_run.error_message = "StaleRun: no progress for 30 minutes (process interrupted)"
            active_run.completed_at = now

        # 3. Load segments
        seg_stmt = select(MarketSegments).where(MarketSegments.study_id == study_id)
        if segmentation_run_id:
            seg_stmt = seg_stmt.where(MarketSegments.segmentation_run_id == segmentation_run_id)
        if user_id:
            seg_stmt = seg_stmt.where(MarketSegments.user_id == user_id)
        if not segmentation_run_id:
            newest_run = (
                seg_stmt.with_only_columns(MarketSegments.segmentation_run_id)
                .order_by(MarketSegments.created_at.desc(), MarketSegments.id.desc())
                .limit(1)
                .correlate(None)
                .scalar_subquery()
            )
            seg_stmt = seg_stmt.where(MarketSegments.segmentation_run_id == newest_run)
        seg_stmt = seg_stmt.order_by(MarketSegments.created_at.desc(), MarketSegments.id.desc())
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
        )
        if self.ml_generator is None:
            claim_stmt = claim_stmt.limit(_CLAIM_FETCH_LIMIT)
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
        run_id = existing_run_id or f"pgen_{uuid.uuid4().hex[:12]}"
        if run is None:
            run = PersonaGenerationRuns(id=run_id, study_id=study_id, user_id=user_id)
            self.session.add(run)
        run.segmentation_run_id = target_seg_run_id
        run.status = "generating_personas"
        run.configuration = {
            "personas_per_segment": personas_per_segment,
            "target_count": final_target_count,
            "distribution_strategy": distribution_strategy,
        }
        run.target_count = final_target_count
        run.generated_count = 0
        run.valid_count = 0
        run.warning_count = 0
        run.dataset_versions = dataset_snapshots
        run.evidence_snapshot = evidence_snapshot
        run.started_at = _utcnow()
        run.completed_at = None
        run.error_message = None
        if job is not None:
            run.configuration = {**run.configuration, "job_id": job["job_id"], "input_versions": expected_input_versions}
            await self.session.flush()
            job["result_refs"] = {"run_id": run_id}
            await self.session.execute(update(DurableJobs).where(DurableJobs.id == job["job_id"]).values(result_refs={"run_id": run_id}))
        await self.session.commit()

        # Step 6: Generate Personas
        try:
            exclude_ids: set[str] = set()
            exclude_names: set[str] = set()
            if self.ml_generator is not None:
                study = cast(Studies, await lock_persona_parent(
                    self.session, owner_id=owner_id, study_id=study_id,
                ))
                await self._require_generating_run(study_id, run_id, user_id)
                exclude_ids, exclude_names = await active_source_exclusions(
                    self.session, owner_id=owner_id, study_id=study_id,
                    scope=Personas.study_id == study_id,
                )
            drafts = await generate_personas_for_study(
                study=study,
                segments=segments,
                target_count=final_target_count,
                distribution_strategy=distribution_strategy,
                datasets=datasets,
                evidence_claims=claims,
                llm_service=self.llm_service,
                ml_generator=self.ml_generator,
                exclude_ids=exclude_ids,
                exclude_names=exclude_names,
            )

            if self.ml_generator is None:
                study = cast(Studies, await lock_persona_parent(
                    self.session, owner_id=owner_id, study_id=study_id,
                ))
                await self._require_generating_run(study_id, run_id, user_id)
            if expected_input_versions is not None and await capture_persona_input_versions(self.session, study_id) != expected_input_versions:
                raise APIError(409, "Persona inputs changed during generation.", error_code="persona_input_changed")
            run.status = "saving_personas"

            persisted_personas: list[Personas] = []
            valid_count = 0
            warning_count = 0

            # Drafts know their segment; fall back to the first segment only for
            # drafts produced by callers that did not stamp one.
            seg_ids = {s.id for s in segments}
            seg_id_fallback = segments[0].id

            for idx, draft in enumerate(drafts):
                matched_sid = draft.segment_id if draft.segment_id in seg_ids else seg_id_fallback

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
                    # provider/model) — never a fabricated constant.
                    generation_model=draft.generation_model,
                    archetype=draft.archetype,
                    tagline=draft.tagline,
                    country_code=draft.country_code,
                    personality=draft.personality or {},
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
            await self.session.flush()
            for persona in persisted_personas:
                await record_persona_version(self.session, persona)
            await refresh_study_persona_state(
                self.session, study=study, owner_id=owner_id, removed_ids=set(),
            )
            study.step = max(study.step, 3)

            if job is not None:
                references = {"run_id": run_id, "persona_versions": [{"id": persona.id, "version": persona.version} for persona in persisted_personas]}
                await job.complete_item("persona_generation", result_refs=references, session=self.session)
                job["result_refs"] = references
            await self.session.commit()
            return run, persisted_personas

        except Exception as exc:
            await self.session.rollback()
            if isinstance(exc, LeaseLost):
                raise
            failed_run = await self.get_run(study_id, run_id, user_id)
            error_summary = safe_error_summary(exc)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_message = error_summary
                failed_run.completed_at = _utcnow()
            logger.error(
                "persona generation run %s failed: %s", run_id, error_summary
            )
            await self.session.commit()
            raise

    async def _require_generating_run(
        self, study_id: str, run_id: str, user_id: Optional[str],
    ) -> None:
        statement = select(PersonaGenerationRuns).where(
            PersonaGenerationRuns.id == run_id, PersonaGenerationRuns.study_id == study_id,
            func.coalesce(PersonaGenerationRuns.user_id, "usr_system_holder") == (user_id or "usr_system_holder"),
        ).execution_options(populate_existing=True)
        run = (await self.session.execute(statement)).scalar_one_or_none()
        if run is None or run.status != "generating_personas":
            raise APIError(409, "The persona generation run is no longer active.", error_code="data_integrity")

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
            .join(Studies, Studies.id == Personas.study_id)
            .where(
                Personas.study_id == study_id,
                Personas.owner_id == func.coalesce(Studies.user_id, "usr_system_holder"),
            )
            .order_by(Personas.created_at.desc())
        )
        if user_id:
            stmt = stmt.where(Personas.owner_id == user_id)
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
        stmt = select(Personas).join(Studies, Studies.id == Personas.study_id).where(
            Personas.id == persona_id,
            Personas.study_id == study_id,
            Personas.owner_id == func.coalesce(Studies.user_id, "usr_system_holder"),
        )
        if user_id:
            stmt = stmt.where(Personas.owner_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def regenerate_persona(
        self, study_id: str, persona_id: str, user_id: Optional[str] = None
    ) -> Personas:
        """Regenerate a single persona to create a new version while preserving grounding."""
        try:
            return await self._regenerate_persona(study_id, persona_id, user_id)
        except IntegrityError as exc:
            await self.session.rollback()
            raise APIError(409, "Persona regeneration conflicts with existing data.", error_code="data_integrity") from exc
        except BaseException:
            await self.session.rollback()
            raise

    async def _regenerate_persona(
        self, study_id: str, persona_id: str, user_id: Optional[str],
    ) -> Personas:
        owner_id = user_id or "usr_system_holder"
        if self.ml_generator is not None:
            await lock_persona_parent(self.session, owner_id=owner_id, study_id=study_id)
        persona = await self.get_persona(study_id, persona_id, user_id)
        if persona is None or persona.owner_id != owner_id:
            raise ValueError(f"Persona '{persona_id}' not found.")
        await self.session.refresh(persona)
        previous_version = persona.version

        # Load segment
        segment = None
        if persona.segment_id:
            segment = await self.session.get(MarketSegments, persona.segment_id)

        # Load claims
        claim_stmt = select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
        claims = list((await self.session.execute(claim_stmt)).scalars().all())

        study = await self.session.get(Studies, study_id)

        # Generate fresh draft
        if segment is None:
            raise ValueError(
                f"Persona '{persona_id}' has no market segment to regenerate against; run segmentation first."
            )
        exclude_ids: set[str] = set()
        exclude_names: set[str] = set()
        if self.ml_generator is not None:
            exclude_ids, exclude_names = await active_source_exclusions(
                self.session, owner_id=owner_id, study_id=study_id,
                scope=Personas.study_id == study_id,
            )
        else:
            await self.session.commit()
        drafts = await generate_personas_for_study(
            study=study,
            segments=[segment],
            target_count=1,
            distribution_strategy="equal",
            evidence_claims=claims,
            llm_service=self.llm_service,
            ml_generator=self.ml_generator,
            exclude_ids=exclude_ids,
            exclude_names=exclude_names,
        )
        if drafts:
            if self.ml_generator is None:
                await lock_persona_parent(self.session, owner_id=owner_id, study_id=study_id)
                current_persona = await self.get_persona(study_id, persona_id, user_id)
                if current_persona is None:
                    raise APIError(409, "The persona was deleted during regeneration.", error_code="data_integrity")
                await self.session.refresh(current_persona)
                if current_persona.version != previous_version:
                    raise APIError(409, "The persona changed during regeneration.", error_code="data_integrity")
                persona = current_persona
            await record_persona_version(self.session, persona, capture_kind="observed_current")
            draft = drafts[0]
            persona.version += 1
            persona.name = draft.name
            persona.generation_model = draft.generation_model
            persona.archetype = draft.archetype
            persona.tagline = draft.tagline
            persona.country_code = draft.country_code
            persona.personality = draft.personality or {}
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
            await record_persona_version(self.session, persona)
            if study is not None:
                await refresh_study_persona_state(
                    self.session, study=study, owner_id=owner_id, removed_ids=set(),
                )
            await self.session.commit()
        else:
            await self.session.commit()

        return persona
