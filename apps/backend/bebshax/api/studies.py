"""FastAPI routes for research studies and persona library audience persistence."""

import logging
from datetime import datetime, timezone
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import MetaData, Table, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql import ColumnElement

from bebshax.auth.models import Users
from bebshax.auth.security import decode_access_token
from bebshax.api.deps import (
    get_tenant_user as get_current_user,
    get_optional_tenant_user as get_optional_current_user,
    get_session,
    owner_accessible,
    owner_can_write,
    require_study_access,
    user_owns_study,
)
from bebshax.api.evidence import start_study_research as trigger_study_research
from bebshax.api.limiter import _client_key, limiter
from bebshax.api.jobs import cancel_job_async, get_job_async, replay_job_input, run_job_inline, start_job_async
from bebshax.datasets.service import enqueue_dataset_cleanup
from bebshax.db.models import Base, DatasetSources, SavedAudiences, Studies, StudyReports
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.jobs.runtime import JobContext
from bebshax.llm.json_utils import parse_llm_json, unwrap_list
from bebshax.llm.placeholders import is_placeholder
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.tenancy import PUBLIC_OWNER_IDS as _PUBLIC_OWNER_IDS
from bebshax.tenancy_context import tenant_scope
from bebshax.utils.explicit_failures import InsufficientInput, LLMUnavailable, UnusableModelOutput
from bebshax.utils.title_generator import clean_client_title, generate_deterministic_study_title
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.report_service import StudyReportService, capture_report_input_versions
from bebshax.persona.context import private_persona_context
from bebshax.personas.service import canonical_study_persona_states, canonical_study_persona_summaries

logger = logging.getLogger(__name__)

router = APIRouter(tags=["studies"])

# An unusable script reply is retried once with the same request, then refused.
_SCRIPT_MAX_ATTEMPTS = 2

# Back-compat aliases: api/payments.py (frozen path) and any straggler still
# import the old underscore-private names from this module. New code should
# import the public names from bebshax.api.deps instead.
_user_owns_study = user_owns_study
_owner_accessible = owner_accessible

# Column widths from db/models.py Studies; oversized values used to surface as
# a PG DataError 500 (invisible on the sqlite test DB).
_SHORT = 64  # type / goal / status
_TITLE = 256
_DURATION = 128
_LONG_TEXT = 20_000  # Text columns: prompt / target_audience / pricing_hypothesis
_DERIVED_STUDY_FIELDS = frozenset({"persona_count", "persona_ids", "personas_data", "findings"})


class StudyCreateRequest(BaseModel):
    # Accepted for API compatibility only — the server always generates the id.
    id: Optional[str] = Field(default=None, max_length=_SHORT)
    user_id: Optional[str] = Field(default=None, max_length=_SHORT)
    title: Optional[str] = Field(default=None, max_length=_TITLE)
    type: str = Field(default="interviews", max_length=_SHORT)
    study_type: Optional[str] = Field(default=None, max_length=_SHORT)
    goal: str = Field(default="demand_validation", max_length=_SHORT)
    prompt: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    product_idea: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    target_audience: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    pricing_hypothesis: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    status: str = Field(default="draft", max_length=_SHORT)
    step: int = Field(default=1, ge=0, le=100)
    persona_count: int = Field(default=0, ge=0)
    persona_ids: list[str] = Field(default_factory=list)
    suggested_roles: list[dict[str, Any]] = Field(default_factory=list)
    script_questions: list[str] = Field(default_factory=list)
    findings: Optional[dict[str, Any]] = None
    is_demo: bool = False
    duration_text: Optional[str] = Field(default=None, max_length=_DURATION)
    copilot_messages: Optional[list[dict[str, Any]]] = None
    personas_data: Optional[list[dict[str, Any]]] = None


class StudyUpdateRequest(BaseModel):
    user_id: Optional[str] = Field(default=None, max_length=_SHORT)
    title: Optional[str] = Field(default=None, max_length=_TITLE)
    type: Optional[str] = Field(default=None, max_length=_SHORT)
    study_type: Optional[str] = Field(default=None, max_length=_SHORT)
    goal: Optional[str] = Field(default=None, max_length=_SHORT)
    prompt: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    product_idea: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    target_audience: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    pricing_hypothesis: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    status: Optional[str] = Field(default=None, max_length=_SHORT)
    step: Optional[int] = Field(default=None, ge=0, le=100)
    persona_count: Optional[int] = Field(default=None, ge=0)
    persona_ids: Optional[list[str]] = None
    suggested_roles: Optional[list[dict[str, Any]]] = None
    script_questions: Optional[list[str]] = None
    findings: Optional[dict[str, Any]] = None
    is_demo: Optional[bool] = None
    duration_text: Optional[str] = Field(default=None, max_length=_DURATION)
    copilot_messages: Optional[list[dict[str, Any]]] = None
    personas_data: Optional[list[dict[str, Any]]] = None
    expected_revision: int | None = Field(default=None, ge=1, le=2_147_483_647, strict=True)

    @model_validator(mode="after")
    def reject_guarded_derived_state(self) -> "StudyUpdateRequest":
        if self.expected_revision is not None and self.model_fields_set & _DERIVED_STUDY_FIELDS:
            raise ValueError("Persona state and findings are server-generated and read-only.")
        return self


class AudienceCreateRequest(BaseModel):
    id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    user_id: Optional[str] = Field(default=None, max_length=_SHORT)
    study_id: Optional[str] = Field(default=None, max_length=_SHORT)
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    persona_ids: list[str] = Field(default_factory=list, max_length=200)
    personas_payload: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    role_distribution: dict[str, Any] = Field(default_factory=dict)


def _account_or_client_key(request: Request) -> str:
    """slowapi ``key_func``: budget study creation per signed-in account. A signature
    check (no DB) suffices — a forged token still lands in its own bucket and is
    rejected by authentication before any write."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_access_token(auth.split(" ", 1)[1].strip())
        if payload and payload.get("sub"):
            return f"account:{payload['sub']}"
    return _client_key(request)


_STEP_LABELS = {1: "Context", 2: "Personas", 3: "Script", 4: "Interviews", 5: "Report"}


def _study_summary_text(s: Studies) -> str:
    """Progress line derived from state; the stored value was written at creation and went stale."""
    count = s.persona_count or 0
    personas = f"{count} synthetic persona{'' if count == 1 else 's'}"
    if s.status == "completed":
        return f"Completed • {'Decision report ready' if s.findings else 'Report pending'} • {personas}"
    step = s.step or 1
    label = _STEP_LABELS.get(step)
    stage = f"Step {step} {label}" if label else f"Step {step}"
    if step <= 1 and count == 0:
        return f"Just created • {stage}"
    return f"In Progress • {stage} • {personas if count else 'No personas yet'}"


def _serialize_study(
    s: Studies, persona_state: dict[str, Any] | None = None, *, summary: bool = False,
) -> dict[str, Any]:
    """``summary`` is the list shape: no chat history and no persona rows, which
    the dashboard never reads there and which grow without bound otherwise."""
    result = {
        "id": s.id,
        "revision": s.revision,
        "user_id": s.user_id,
        "title": s.title,
        "type": s.type,
        "study_type": s.type,
        "goal": s.goal,
        "prompt": s.prompt,
        "product_idea": s.prompt,
        "target_audience": s.target_audience,
        "pricing_hypothesis": s.pricing_hypothesis,
        "status": s.status,
        "step": s.step,
        "persona_count": s.persona_count,
        "persona_ids": s.persona_ids or [],
        "suggested_roles": s.suggested_roles or [],
        "script_questions": s.script_questions or [],
        "script_meta": s.script_meta,
        "findings": s.findings,
        "is_demo": s.is_demo,
        "duration_text": _study_summary_text(s),
        "copilot_messages": s.copilot_messages or [],
        "personas_data": s.personas_data or [],
        "created_at": s.created_at.isoformat() if s.created_at else datetime.now(timezone.utc).isoformat(),
        "updated_at": s.updated_at.isoformat() if s.updated_at else datetime.now(timezone.utc).isoformat(),
    }
    if summary:
        del result["copilot_messages"], result["personas_data"]
    if persona_state is not None:
        result.update(persona_state)
    return result


def _expected_revision(if_match: str | None, payload: StudyUpdateRequest) -> int | None:
    if if_match is None:
        return payload.expected_revision
    condition = if_match.strip()
    value = condition[1:-1] if condition.startswith('"') and condition.endswith('"') else condition
    if not 1 <= len(value) <= 10 or not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 2_147_483_647:
        raise HTTPException(status_code=400, detail="If-Match must contain one positive study revision.")
    revision = int(value)
    if payload.expected_revision is not None and payload.expected_revision != revision:
        raise HTTPException(status_code=400, detail="If-Match and expected_revision disagree.")
    if payload.model_fields_set & _DERIVED_STUDY_FIELDS:
        raise HTTPException(status_code=422, detail="Persona state and findings are server-generated and read-only.")
    return revision


def _serialize_audience(a: SavedAudiences) -> dict[str, Any]:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "study_id": a.study_id,
        "name": a.name,
        "description": a.description,
        "persona_ids": a.persona_ids or [],
        "personas_payload": a.personas_payload or [],
        "role_distribution": a.role_distribution or {},
        "created_at": a.created_at.isoformat() if a.created_at else datetime.now(timezone.utc).isoformat(),
        "updated_at": a.updated_at.isoformat() if a.updated_at else datetime.now(timezone.utc).isoformat(),
    }


def _serialize_report(r: StudyReports) -> dict[str, Any]:
    return {
        "id": r.id,
        "study_id": r.study_id,
        "user_id": r.user_id,
        "version": r.version,
        "title": r.title,
        "executive_summary": r.executive_summary,
        "key_findings": r.key_findings or [],
        "target_market_summary": r.target_market_summary,
        "market_context_summary": r.market_context_summary,
        "evidence_findings": r.evidence_findings or [],
        "dataset_findings": r.dataset_findings or [],
        "market_segments_summary": r.market_segments_summary or [],
        "persona_overview": r.persona_overview or [],
        "interview_findings": r.interview_findings or [],
        "major_pain_points": r.major_pain_points or [],
        "customer_needs": r.customer_needs or [],
        "behavioral_results": r.behavioral_results or [],
        "pricing_signals": r.pricing_signals or [],
        "major_risks": r.major_risks or [],
        "opportunities": r.opportunities or [],
        "strongest_segments": r.strongest_segments or [],
        "recommendations": r.recommendations or [],
        "validation_summary": r.validation_summary,
        "limitations": r.limitations,
        "metrics": r.metrics or {},
        "is_synthetic": r.is_synthetic,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


class GenerateReportRequest(BaseModel):
    title: Optional[str] = None


class GenerateScriptRequest(BaseModel):
    prompt: Optional[str] = None
    question_count: int = Field(default=5, ge=3, le=10)


# ============================================================================
# Studies
# ============================================================================

@router.get("/studies", response_model=list[dict[str, Any]])
async def list_studies(
    user_id: Optional[str] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List research studies for the current user only (+ public demo studies).

    The `user_id` query param is accepted for API compatibility but ignored —
    identity comes exclusively from the auth token (impersonation guard).
    Anonymous callers see only explicitly classified demo studies.
    """
    del user_id  # never trust client-supplied identity
    if current_user:
        stmt = select(Studies).where(
            or_(Studies.user_id == current_user.id, Studies.is_demo == True)
        ).order_by(Studies.created_at.desc())
    else:
        stmt = select(Studies).where(
            Studies.is_demo.is_(True)
        ).order_by(Studies.created_at.desc())
    result = await session.execute(stmt)
    studies = list(result.scalars().all())
    summaries = await canonical_study_persona_summaries(session, studies)
    return [_serialize_study(study, summaries[study.id], summary=True) for study in studies]


@router.post("/studies", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/hour", key_func=_account_or_client_key)
async def create_study(
    request: Request,
    response: Response,
    payload: StudyCreateRequest,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new research study for the authenticated user with deterministic title."""
    effective_prompt = (payload.prompt or payload.product_idea or "").strip()
    provided_title = clean_client_title(payload.title)
    study_type = payload.type or payload.study_type or "interviews"

    # Input validation: reject empty prompt and empty title
    if not effective_prompt and not provided_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Describe your product idea before starting the study.",
        )

    # Determine title deterministically if missing or generic
    if provided_title and provided_title != "Untitled Study":
        title = provided_title
    else:
        title = generate_deterministic_study_title(effective_prompt, study_type)

    # The primary key is never client-chosen: a caller-picked id let one
    # visitor collide with (or probe for) another's study. The frontend never
    # sends one on create.
    study_id = f"study_{uuid.uuid4().hex[:16]}"
    # Identity comes from the token only — payload.user_id would let any
    # caller attach rows to another tenant (spoofing).
    study_user_id = current_user.id

    study = Studies(
        id=study_id,
        user_id=study_user_id,
        title=title,
        type=study_type,
        goal=payload.goal,
        prompt=effective_prompt or None,
        target_audience=(payload.target_audience or "").strip() or None,
        pricing_hypothesis=(payload.pricing_hypothesis or "").strip() or None,
        status=payload.status,
        step=payload.step,
        persona_count=0,
        persona_ids=[],
        suggested_roles=payload.suggested_roles,
        script_questions=payload.script_questions,
        findings=None,
        # Never from the client: is_demo makes a study (and its personas)
        # world-readable, so only the seed may flag it.
        is_demo=False,
        duration_text=payload.duration_text,
        copilot_messages=payload.copilot_messages,
        personas_data=[],
    )
    session.add(study)
    try:
        await session.flush()
        await session.refresh(study)
        result = _serialize_study(study)
        response.headers["ETag"] = f'"{study.revision}"'
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return result


@router.get("/studies/{study_id}")
async def get_study(
    study_id: str,
    response: Response,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a research study by ID. Returns 404 if not found or not owned by caller."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    states = await canonical_study_persona_states(session, [study])
    response.headers["ETag"] = f'"{study.revision}"'
    return _serialize_study(study, states[study.id])


@router.patch("/studies/{study_id}")
@router.put("/studies/{study_id}")
async def update_study(
    study_id: str,
    payload: StudyUpdateRequest,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update existing owned state; opt-in revisions protect full-history saves."""
    study = require_study_access(await session.get(Studies, study_id), current_user, write=True)
    expected = _expected_revision(if_match, payload)
    conflict_status = 412 if if_match is not None else 409
    if expected is not None and expected != study.revision:
        raise HTTPException(status_code=conflict_status, detail="Study changed; reload before saving.")
    if expected is None and payload.copilot_messages is not None:
        stored_messages = study.copilot_messages or []
        if payload.copilot_messages[:len(stored_messages)] != stored_messages:
            raise HTTPException(status_code=409, detail="Study history changed; reload before saving.")
    states = await canonical_study_persona_states(session, [study])
    update_data = payload.model_dump(exclude_unset=True, exclude=set(_DERIVED_STUDY_FIELDS) | {"expected_revision"})
    if "product_idea" in update_data and "prompt" not in update_data:
        update_data["prompt"] = update_data["product_idea"]
    if "study_type" in update_data and "type" not in update_data:
        update_data["type"] = update_data["study_type"]

    # Identity/PK fields are never mass-assignable — a payload user_id would
    # re-attach the study to an arbitrary tenant (spoofing), and is_demo would
    # make it world-readable.
    update_data.pop("id", None)
    update_data.pop("user_id", None)
    update_data.pop("is_demo", None)
    if isinstance(update_data.get("title"), str):
        # The frontend derives titles by slicing the raw prompt; markup in the
        # prompt must not become markup in the title.
        update_data["title"] = clean_client_title(update_data["title"]) or None

    for field, val in update_data.items():
        if val is not None and hasattr(study, field):
            setattr(study, field, val)

    for field, value in states[study.id].items():
        setattr(study, field, value)
    study.updated_at = datetime.now(timezone.utc)
    try:
        await session.flush()
        result = _serialize_study(study)
        response.headers["ETag"] = f'"{study.revision}"'
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise HTTPException(status_code=conflict_status, detail="Study changed; reload before saving.") from exc
    except Exception:
        await session.rollback()
        raise
    return result


# Tables that carry study attribution for audit/retention but are historical
# records: they must outlive the study they describe, never cascade with it.
RETAINED_ON_STUDY_DELETE: frozenset[str] = frozenset({"llm_requests"})


def study_scoped_tables(metadata: MetaData = Base.metadata) -> dict[str, Table]:
    """Every table a study delete must empty: all tables with a ``study_id``
    column, plus (transitively) every table whose foreign key points at one of
    those — persona details/attributes/evidence and memories hang off
    ``personas``, turns and insights off ``conversations``, scenarios/results
    off behavioral tests/runs. Computed from the live metadata so a new table
    is covered the moment it is declared, never by a hand-kept list.
    ``llm_requests`` (provenance) has no FKs by design and is kept even though
    it records the study it served."""
    studies = metadata.tables["studies"]
    scoped: dict[str, Table] = {
        t.name: t for t in metadata.sorted_tables
        if t is not studies and "study_id" in t.c and t.name not in RETAINED_ON_STUDY_DELETE
    }
    changed = True
    while changed:
        changed = False
        for t in metadata.sorted_tables:
            if t is studies or t.name in scoped or t.name in RETAINED_ON_STUDY_DELETE:
                continue
            if any(constraint.referred_table.name in scoped for constraint in t.foreign_key_constraints):
                scoped[t.name] = t
                changed = True
    return scoped


def _scoped_rows(
    table: Table, study_id: str, scoped: dict[str, Table], seen: frozenset[str] = frozenset()
) -> ColumnElement[bool]:
    """Rows of ``table`` that belong to the study directly (``study_id``) or
    through a complete foreign-key constraint into another scoped table."""
    clauses: list[ColumnElement[bool]] = []
    if "study_id" in table.c:
        clauses.append(table.c.study_id == study_id)
    for constraint in table.foreign_key_constraints:
        parent = constraint.referred_table
        if parent.name in scoped and parent is not table and parent.name not in seen:
            parent_rows = _scoped_rows(parent, study_id, scoped, seen | {table.name})
            clauses.append(
                select(1).select_from(parent).where(
                    parent_rows,
                    *(element.parent == element.column for element in constraint.elements),
                ).correlate(table).exists()
            )
    return or_(False, *clauses)


def study_cascade_deletes(study_id: str, metadata: MetaData = Base.metadata) -> list[Any]:
    """Ordered DELETE statements (children first) that remove everything owned
    by ``study_id`` except the ``studies`` row itself."""
    scoped = study_scoped_tables(metadata)
    return [
        delete(t).where(_scoped_rows(t, study_id, scoped))
        for t in reversed(metadata.sorted_tables)
        if t.name in scoped
    ]


@router.delete("/studies/{study_id}")
async def delete_study(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete study records atomically; journal dataset files for deferred cleanup.

    404 when missing or unreadable; 403 for readable-but-not-writable.
    """
    study = await session.get(Studies, study_id, with_for_update=True)
    study = require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )
    try:
        datasets = (await session.scalars(
            select(DatasetSources).where(DatasetSources.study_id == study_id).with_for_update()
        )).all()
        for dataset in datasets:
            await enqueue_dataset_cleanup(session, dataset)

        # Metadata-driven cascade: a hand-written list used to cover 8 tables and
        # left personas, conversations, runs, reports and behavioral rows orphaned
        # (and still readable).
        for stmt in study_cascade_deletes(study_id):
            await session.execute(stmt)

        await session.delete(study)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return {"success": True, "deleted_id": study_id}


# ============================================================================
# Persona Library: Saved Audiences Persistence
# ============================================================================

@router.get("/audiences", response_model=list[dict[str, Any]])
async def list_saved_audiences(
    user_id: Optional[str] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List saved audiences for the caller (+ shared/unowned rows).

    The `user_id` query param is ignored — identity comes from the token.
    """
    del user_id  # never trust client-supplied identity
    shared = or_(SavedAudiences.user_id == None, SavedAudiences.user_id.in_(_PUBLIC_OWNER_IDS))
    if current_user:
        stmt = select(SavedAudiences).where(
            or_(SavedAudiences.user_id == current_user.id, shared)
        ).order_by(SavedAudiences.created_at.desc())
    else:
        stmt = select(SavedAudiences).where(shared).order_by(SavedAudiences.created_at.desc())
    result = await session.execute(stmt)
    audiences = list(result.scalars().all())
    return [_serialize_audience(a) for a in audiences]


@router.post("/audiences", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/hour")
async def save_audience(
    request: Request,
    payload: AudienceCreateRequest,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Save an audience to the Persona Library. Saved audiences are private writes:
    anonymous callers never file rows into the shared pool."""
    # Body-supplied study id: a caller must at least be allowed to see the
    # study they are filing an audience under.
    if payload.study_id:
        linked_study = await session.get(Studies, payload.study_id)
        if not linked_study or not user_owns_study(linked_study, current_user):
            raise HTTPException(status_code=404, detail=f"Study '{payload.study_id}' not found")
    audience_id = payload.id or f"aud_{uuid.uuid4().hex[:16]}"
    # Identity from the token only (never payload.user_id — spoofing).
    aud_user_id = current_user.id
    audience = SavedAudiences(
        id=audience_id,
        user_id=aud_user_id,
        study_id=payload.study_id,
        name=payload.name,
        description=payload.description,
        persona_ids=payload.persona_ids,
        personas_payload=payload.personas_payload,
        role_distribution=payload.role_distribution,
    )
    session.add(audience)
    await session.commit()
    await session.refresh(audience)
    return _serialize_audience(audience)


@router.delete("/audiences/{audience_id}")
async def delete_audience(
    audience_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Remove a saved audience from the Persona Library."""
    audience = await session.get(SavedAudiences, audience_id)
    if not audience:
        raise HTTPException(status_code=404, detail=f"Audience '{audience_id}' not found")
    # Destroying a row is not a read: the shared pool is readable by everyone
    # but deletable only by the row's own owner (bebshax/tenancy.owner_can_write).
    if not owner_can_write(audience.user_id, current_user):
        # 404 (not 403) — do not confirm the row exists to non-owners.
        raise HTTPException(status_code=404, detail=f"Audience '{audience_id}' not found")
    await session.delete(audience)
    await session.commit()
    return {"success": True, "deleted_id": audience_id}


# ============================================================================
# Dynamic Script Questions Generation
# ============================================================================

@router.post("/studies/{study_id}/script/generate")
@limiter.limit("20/minute")
async def generate_script_questions(
    study_id: str,
    request: Request,
    payload: Optional[GenerateScriptRequest] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate dynamic, context-specific interview script questions for a study."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: this overwrites study.script_questions, and a 403
    # on a foreign non-demo study would confirm its existence.
    study = require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    # Never the title: a title-only study produced a script full of placeholders
    # ("[specific metric relevant to the business idea]") — fabrication, not research.
    prompt = ((payload.prompt if payload else None) or study.prompt or "").strip()
    if not prompt:
        raise InsufficientInput(
            "business_description_required",
            "Describe the business idea before generating a script.",
        )
    q_count = (payload and payload.question_count) or 5
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    owner_id = current_user.id
    context_revision = study.revision

    llm_service = getattr(request.app.state, "llm_service", None) if request else None
    if llm_service is None:
        raise LLMUnavailable("Interview script generation")

    sys_prompt = (
        "You are BebshaX Research Script Architect. Generate high-impact, open-ended qualitative "
        "interview questions for validating a customer discovery hypothesis. "
        "Do not ask leading questions. Focus on discovering current habits, existing workarounds, "
        "frustrations, willingness to pay, and decision-making criteria. Every question must be "
        "specific to the study context below — never generic. "
        'Return ONLY a JSON object with one key "questions" holding an array of strings, '
        'e.g. {"questions": ["Question 1", "Question 2"]}. '
        + UNTRUSTED_RULE
    )
    context_lines = [f"BUSINESS IDEA: {prompt}"]
    if study.target_audience:
        context_lines.append(f"TARGET AUDIENCE: {study.target_audience}")
    if study.pricing_hypothesis:
        context_lines.append(f"PRICING HYPOTHESIS: {study.pricing_hypothesis}")
    if study.goal:
        context_lines.append(f"RESEARCH GOAL: {study.goal}")
    user_msg = (
        untrusted_block("STUDY_CONTEXT", "\n".join(context_lines), source="study")
        + f"\nGenerate exactly {q_count} sequential interview questions inside the \"questions\" array."
    )
    req = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content=sys_prompt),
            ChatMessage(role="user", content=user_msg),
        ],
        json_mode=True,
        temperature=0.4,
        owner_user_id=owner_id,
        study_id=study_id,
        data_classification="private",
    )
    session.expunge_all()
    await session.rollback()

    def _questions_of(parsed: Any) -> list[str]:
        items = unwrap_list(parsed, keys=("questions", "interview_questions", "script"))
        questions = [str(q).strip() for q in items if isinstance(q, (str, int, float)) and str(q).strip()]
        # The prompt's own example ("Question 1") echoed back is not a question.
        return [q for q in questions if not is_placeholder(q)]

    generated_questions: list[str] = []
    res = None
    attempts = 0
    for attempts in range(1, _SCRIPT_MAX_ATTEMPTS + 1):
        if attempts > 1:
            req = req.retry_copy()
        with private_persona_context(owner_id, study_id):
            res = await llm_service.complete(req)
        try:
            parsed = parse_llm_json(res.text)
        except ValueError:
            parsed = None
        generated_questions = _questions_of(parsed)
        if len(generated_questions) >= 2:
            break
        logger.warning("script generation reply unusable for study %s (attempt %d)", study_id, attempts)
        generated_questions = []
    if res is None or not generated_questions:
        raise UnusableModelOutput(
            "script_unparseable",
            f"The model's reply could not be turned into interview questions after {attempts} attempts; "
            "no template was substituted. Please try again.",
            attempts=attempts,
            served_by=f"{res.provider}/{res.model}" if res is not None else None,
        )

    served_by = f"{res.provider}/{res.model}"
    llm_request_id = getattr(getattr(res, "provenance", None), "request_id", None)
    study = require_study_access(
        await session.get(Studies, study_id, with_for_update=True), current_user, write=True,
    )
    if study.revision != context_revision:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Study changed during script generation; reload and retry.")
    study.script_questions = generated_questions
    study.script_meta = {
        "source": "llm",
        "served_by": served_by,
        "llm_request_id": llm_request_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attempts": attempts,
    }
    study.updated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except StaleDataError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Study changed during script generation; reload and retry.") from exc

    return {
        "study_id": study_id,
        "questions": generated_questions,
        "count": len(generated_questions),
        "source": "llm",
        "served_by": served_by,
        "llm_request_id": llm_request_id,
        "fallback_reason": "retried_after_unparseable_reply" if attempts > 1 else None,
        # The save above advanced the revision; the client adopts it instead of
        # re-sending the same questions against the stale one (412).
        "study_revision": study.revision,
    }


# ============================================================================
# Autonomous Research Trigger & Status
# ============================================================================

router.add_api_route(
    "/studies/{study_id}/research/run",
    trigger_study_research,
    methods=["POST"],
    status_code=status.HTTP_202_ACCEPTED,
    name="trigger_study_research",
)


# ============================================================================
# Comprehensive Study Reports Persistence & Generation
# ============================================================================

@router.get("/studies/{study_id}/reports")
async def list_study_reports(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List all report versions for a study."""
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, not_found_detail=f"Study '{study_id}' not found")

    stmt = select(StudyReports).where(StudyReports.study_id == study_id).order_by(StudyReports.version.desc())
    reports = list((await session.execute(stmt)).scalars().all())
    return [_serialize_report(r) for r in reports]


@router.get("/studies/{study_id}/reports/latest")
async def get_latest_study_report(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the latest report version for a study."""
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, not_found_detail=f"Study '{study_id}' not found")

    stmt = select(StudyReports).where(StudyReports.study_id == study_id).order_by(StudyReports.version.desc()).limit(1)
    report = (await session.execute(stmt)).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail=f"No reports generated for study '{study_id}' yet")
    return _serialize_report(report)


@router.get("/studies/{study_id}/reports/{report_id}")
async def get_study_report_by_id(
    study_id: str,
    report_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific report version by ID."""
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, not_found_detail=f"Study '{study_id}' not found")

    report = await session.get(StudyReports, report_id)
    if not report or report.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found for study '{study_id}'")
    return _serialize_report(report)


@router.post("/studies/{study_id}/reports/generate", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def generate_study_report(
    study_id: str,
    request: Request,
    payload: Optional[GenerateReportRequest] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Synthesize and persist a comprehensive research report for the study."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: this persists a StudyReports row and spends LLM budget.
    study = require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    llm_service = getattr(request.app.state, "llm_service", None) if request else None
    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID
    custom_title = payload.title if payload else None
    input_data = {
        "title": custom_title, "study_revision": study.revision,
        "input_versions": await capture_report_input_versions(session, study),
    }
    input_data = await replay_job_input(
        request.app, kind="report_generation", scope_id=study_id, user_id=effective_user_id,
        idempotency_key=request.headers.get("Idempotency-Key"), input_data=input_data,
        snapshot_fields=frozenset({"study_revision", "input_versions"}),
    )
    maker = request.app.state.db_sessionmaker
    await session.rollback()

    async def operation(job: JobContext) -> dict[str, Any]:
        with tenant_scope(effective_user_id):
            async with maker() as job_session:
                report = await StudyReportService(session=job_session, llm_service=llm_service).generate_report(
                    study_id=study_id, user_id=effective_user_id, custom_title=custom_title, job=job,
                    expected_input_versions=input_data["input_versions"],
                )
                return _serialize_report(report)

    return await run_job_inline(
        request.app, kind="report_generation", scope_id=study_id, user_id=effective_user_id,
        input_data=input_data, operation=operation, idempotency_key=request.headers.get("Idempotency-Key"),
    )


# ---------------------------------------------------------------------------
# Async report-generation jobs: synthesis reads every interview and runs LLM
# calls on a 150 s task budget — beyond comfortable HTTP timeouts. POST
# starts a background job (202), the UI polls; the report row is persisted
# by the service; admission and status are durable.
# ---------------------------------------------------------------------------

@router.post("/studies/{study_id}/reports/generate/jobs", status_code=202)
@limiter.limit("10/minute")
async def start_report_generation_job(
    study_id: str,
    request: Request,
    payload: Optional[GenerateReportRequest] = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start report synthesis in the background; poll the job endpoint."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: the job persists a StudyReports row and spends LLM budget.
    study = require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    app = request.app
    sessionmaker_ = getattr(app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    llm_service = getattr(app.state, "llm_service", None)
    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID
    custom_title = payload.title if payload else None
    input_data = {
        "title": custom_title, "study_revision": study.revision,
        "input_versions": await capture_report_input_versions(session, study),
    }
    input_data = await replay_job_input(
        app, kind="report_generation", scope_id=study_id, user_id=effective_user_id,
        idempotency_key=request.headers.get("Idempotency-Key"), input_data=input_data,
        snapshot_fields=frozenset({"study_revision", "input_versions"}),
    )
    await session.rollback()

    async def _runner(job: JobContext) -> None:
        with tenant_scope(effective_user_id):
            await _generate(job)

    async def _generate(job: JobContext) -> None:
        # The request session is gone by now — the job owns its own session.
        async with sessionmaker_() as job_session:
            report_service = StudyReportService(session=job_session, llm_service=llm_service)
            report = await report_service.generate_report(
                study_id=study_id,
                user_id=effective_user_id,
                custom_title=custom_title,
                job=job,
                expected_input_versions=input_data["input_versions"],
            )
            job["result"] = _serialize_report(report)

    job = await start_job_async(
        app,
        kind="report_generation",
        scope_id=study_id,
        runner=_runner,
        user_id=effective_user_id,
        input_data=input_data,
        idempotency_key=request.headers.get("Idempotency-Key"),
        # Honest domain failures (R2/R6) pass their message through.
        user_safe_exceptions=(ContextWindowExceeded, AllCandidatesFailed),
    )
    return {"job_id": job["job_id"], "study_id": study_id, "status": job["status"]}


@router.get("/studies/{study_id}/reports/generate/jobs/{job_id}")
async def get_report_generation_job(
    study_id: str,
    job_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Poll a report-generation job. 404 for unknown/lost jobs (e.g. restart)."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")
    if current_user is None:
        raise HTTPException(status_code=404, detail="job not found")
    job = await get_job_async(
        request.app, job_id, kind="report_generation", scope_id=study_id, user_id=current_user.id,
    )
    if not job:
        raise HTTPException(
            status_code=404,
            detail="job not found (it may have been lost in a server restart)",
        )
    return job


@router.post("/studies/{study_id}/reports/generate/jobs/{job_id}/cancel")
async def cancel_report_generation_job(
    study_id: str, job_id: str, request: Request,
    current_user: Users = Depends(get_current_user), session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found")
    owner_id = current_user.id
    await session.rollback()
    job = await cancel_job_async(
        request.app, job_id, kind="report_generation", scope_id=study_id, user_id=owner_id,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Report job not found")
    return job
