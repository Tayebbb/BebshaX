"""FastAPI routes for research studies and persona library audience persistence."""

import logging
from datetime import datetime, timezone
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import MetaData, Table, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from bebshax.auth.models import Users
from bebshax.auth.security import decode_access_token
from bebshax.api.auth import get_optional_current_user
from bebshax.api.deps import (
    get_session,
    owner_accessible,
    owner_can_write,
    require_study_access,
    user_owns_study,
)
from bebshax.api.limiter import limiter
from bebshax.api.jobs import get_job, start_job
from bebshax.db.models import Base, SavedAudiences, Studies, StudyReports
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.llm.json_utils import parse_llm_json
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.tenancy import PUBLIC_OWNER_IDS as _PUBLIC_OWNER_IDS
from bebshax.utils.title_generator import generate_deterministic_study_title
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.report_service import StudyReportService
from bebshax.research.service import ResearchEngineService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["studies"])

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


class AudienceCreateRequest(BaseModel):
    id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    user_id: Optional[str] = Field(default=None, max_length=_SHORT)
    study_id: Optional[str] = Field(default=None, max_length=_SHORT)
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=_LONG_TEXT)
    persona_ids: list[str] = Field(default_factory=list)
    personas_payload: list[dict[str, Any]] = Field(default_factory=list)
    role_distribution: dict[str, Any] = Field(default_factory=dict)


def _has_valid_bearer_token(request: Request) -> bool:
    """slowapi ``exempt_when``: signed-in callers are exempt from the anonymous
    study-creation limit. A signature check (no DB) is enough here — a garbage
    token is not a way out of the anonymous bucket."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return decode_access_token(auth.split(" ", 1)[1].strip()) is not None


def _serialize_study(s: Studies) -> dict[str, Any]:
    return {
        "id": s.id,
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
        "findings": s.findings,
        "is_demo": s.is_demo,
        "duration_text": s.duration_text or "Just created • No personas yet",
        "copilot_messages": s.copilot_messages or [],
        "personas_data": s.personas_data or [],
        "created_at": s.created_at.isoformat() if s.created_at else datetime.now(timezone.utc).isoformat(),
        "updated_at": s.updated_at.isoformat() if s.updated_at else datetime.now(timezone.utc).isoformat(),
    }


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
    Anonymous callers see demo studies plus the shared anonymous tenant.
    """
    del user_id  # never trust client-supplied identity
    if current_user:
        stmt = select(Studies).where(
            or_(Studies.user_id == current_user.id, Studies.is_demo == True)
        ).order_by(Studies.created_at.desc())
    else:
        stmt = select(Studies).where(
            or_(
                Studies.is_demo == True,
                Studies.user_id.is_(None),
                Studies.user_id.in_(_PUBLIC_OWNER_IDS),
            )
        ).order_by(Studies.created_at.desc())
    result = await session.execute(stmt)
    studies = list(result.scalars().all())
    return [_serialize_study(s) for s in studies]


@router.post("/studies", status_code=status.HTTP_201_CREATED)
# Anonymous creates share one tenant (`usr_default`), so they are the only
# ones that can flood it; signed-in callers are exempt (see the predicate).
@limiter.limit("30/hour", exempt_when=_has_valid_bearer_token)
async def create_study(
    request: Request,
    payload: StudyCreateRequest,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new research study for the authenticated user with deterministic title."""
    effective_prompt = (payload.prompt or payload.product_idea or "").strip()
    provided_title = (payload.title or "").strip()
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
    study_user_id = current_user.id if current_user else ANONYMOUS_OWNER_ID

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
        persona_count=payload.persona_count,
        persona_ids=payload.persona_ids,
        suggested_roles=payload.suggested_roles,
        script_questions=payload.script_questions,
        findings=payload.findings,
        # Never from the client: is_demo makes a study (and its personas)
        # world-readable, so only the seed may flag it.
        is_demo=False,
        duration_text=payload.duration_text,
        copilot_messages=payload.copilot_messages,
        personas_data=payload.personas_data,
    )
    session.add(study)
    await session.commit()
    await session.refresh(study)
    return _serialize_study(study)


@router.get("/studies/{study_id}")
async def get_study(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a research study by ID. Returns 404 if not found or not owned by caller."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    return _serialize_study(study)


@router.patch("/studies/{study_id}")
@router.put("/studies/{study_id}")
async def update_study(
    study_id: str,
    payload: StudyUpdateRequest,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update a research study. Creates it if missing (for seamless workflow init).
    404 when the study exists but the caller cannot read it (existence never
    leaks); 403 only when it is readable but not writable (e.g. the demo).
    """
    study = await session.get(Studies, study_id)
    if not study:
        # Auto-create — supports seamless workflow initialization.
        # Identity from the token only (never payload.user_id — spoofing).
        study_user_id = current_user.id if current_user else ANONYMOUS_OWNER_ID
        prompt = (payload.prompt or payload.product_idea or "").strip()
        study_type = payload.type or payload.study_type or "interviews"
        title = payload.title or (generate_deterministic_study_title(prompt, study_type) if prompt else "Untitled Study")
        study = Studies(
            id=study_id,
            user_id=study_user_id,
            title=title,
            type=study_type,
            goal=payload.goal or "demand_validation",
            prompt=prompt or None,
            target_audience=payload.target_audience,
            pricing_hypothesis=payload.pricing_hypothesis,
        )
        session.add(study)
    else:
        # 404-first via the shared gate: a foreign non-demo study must not be
        # confirmed to exist by a 403 (the write check runs only for readers).
        require_study_access(study, current_user, write=True)
        # Backfill user_id if it was missing (e.g. created anonymously, now logged in).
        # Only from the verified token — payload.user_id would let anonymous
        # callers attach unowned studies to an arbitrary tenant.
        if current_user and not study.user_id:
            study.user_id = current_user.id

    update_data = payload.model_dump(exclude_unset=True)
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

    for field, val in update_data.items():
        if val is not None and hasattr(study, field):
            setattr(study, field, val)

    study.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(study)
    return _serialize_study(study)


def study_scoped_tables(metadata: MetaData = Base.metadata) -> dict[str, Table]:
    """Every table a study delete must empty: all tables with a ``study_id``
    column, plus (transitively) every table whose foreign key points at one of
    those — persona details/attributes/evidence and memories hang off
    ``personas``, turns and insights off ``conversations``, scenarios/results
    off behavioral tests/runs. Computed from the live metadata so a new table
    is covered the moment it is declared, never by a hand-kept list.
    ``llm_requests`` (provenance) has no FKs by design and is kept."""
    studies = metadata.tables["studies"]
    scoped: dict[str, Table] = {
        t.name: t for t in metadata.sorted_tables if t is not studies and "study_id" in t.c
    }
    changed = True
    while changed:
        changed = False
        for t in metadata.sorted_tables:
            if t is studies or t.name in scoped:
                continue
            if any(fk.column.table.name in scoped for fk in t.foreign_keys):
                scoped[t.name] = t
                changed = True
    return scoped


def _scoped_rows(
    table: Table, study_id: str, scoped: dict[str, Table], seen: frozenset[str] = frozenset()
) -> ColumnElement[bool]:
    """Rows of ``table`` that belong to the study directly (``study_id``) or
    through a foreign key into another scoped table (``fk IN (SELECT parent.id
    WHERE <parent belongs to the study>)``)."""
    clauses: list[ColumnElement[bool]] = []
    if "study_id" in table.c:
        clauses.append(table.c.study_id == study_id)
    for fk in table.foreign_keys:
        parent = fk.column.table
        if parent.name in scoped and parent is not table and parent.name not in seen:
            parent_rows = _scoped_rows(parent, study_id, scoped, seen | {table.name})
            clauses.append(fk.parent.in_(select(fk.column).where(parent_rows)))
    return or_(*clauses)


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
    """Delete a research study and all dependent records. 404 when missing or unreadable; 403 for readable-but-not-writable."""
    study = await session.get(Studies, study_id)
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )
    # Metadata-driven cascade: a hand-written list used to cover 8 tables and
    # left personas, conversations, runs, reports and behavioral rows orphaned
    # (and still readable).
    for stmt in study_cascade_deletes(study_id):
        await session.execute(stmt)

    await session.delete(study)
    await session.commit()
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
async def save_audience(
    payload: AudienceCreateRequest,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Save an audience to the Persona Library."""
    # Body-supplied study id: a caller must at least be allowed to see the
    # study they are filing an audience under.
    if payload.study_id:
        linked_study = await session.get(Studies, payload.study_id)
        if not linked_study or not user_owns_study(linked_study, current_user):
            raise HTTPException(status_code=404, detail=f"Study '{payload.study_id}' not found")
    audience_id = payload.id or f"aud_{uuid.uuid4().hex[:16]}"
    # Identity from the token only (never payload.user_id — spoofing).
    aud_user_id = current_user.id if current_user else ANONYMOUS_OWNER_ID
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
    payload: Optional[GenerateScriptRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate dynamic, context-specific interview script questions for a study."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: this overwrites study.script_questions, and a 403
    # on a foreign non-demo study would confirm its existence.
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    prompt = (payload and payload.prompt) or study.prompt or study.title or "Business Idea"
    target_aud = study.target_audience or "Target User"
    pricing = study.pricing_hypothesis or "Market Pricing"
    q_count = (payload and payload.question_count) or 5

    llm_service = getattr(request.app.state, "llm_service", None) if request else None

    generated_questions = []
    fallback_reason: Optional[str] = None if llm_service else "llm_service_unavailable"
    if llm_service:
        try:
            sys_prompt = (
                "You are BebshaX Research Script Architect. Generate high-impact, open-ended qualitative "
                "interview questions for validating a customer discovery hypothesis. "
                "Do not ask leading questions. Focus on discovering current habits, existing workarounds, "
                "frustrations, willingness to pay, and decision-making criteria. "
                "Return ONLY a JSON array of strings, e.g. [\"Question 1\", \"Question 2\", ...]."
            )
            user_msg = (
                f"Business Idea: {prompt}\n"
                f"Target Audience: {target_aud}\n"
                f"Pricing Hypothesis: {pricing}\n"
                f"Generate exactly {q_count} sequential interview questions in JSON array format."
            )
            req = LLMRequest(
                task=TaskType.STRUCTURED_OUTPUT,
                messages=[
                    ChatMessage(role="system", content=sys_prompt),
                    ChatMessage(role="user", content=user_msg),
                ],
                json_mode=True,
                temperature=0.4,
            )
            res = await llm_service.complete(req)
            parsed = parse_llm_json(res.text)
            if isinstance(parsed, list) and len(parsed) >= 2:
                generated_questions = [str(q).strip() for q in parsed if str(q).strip()]
            elif isinstance(parsed, dict) and "questions" in parsed and isinstance(parsed["questions"], list):
                generated_questions = [str(q).strip() for q in parsed["questions"] if str(q).strip()]
            if not generated_questions:
                fallback_reason = "llm_unusable_response"
        except Exception as exc:
            # Same fail-soft to template questions, but loud and marked in the
            # payload so canned questions never impersonate LLM output.
            logger.warning(
                "script-question LLM generation failed for study %s — serving static template questions",
                study_id,
                exc_info=True,
            )
            fallback_reason = f"llm_error:{type(exc).__name__}"

    if not generated_questions:
        generated_questions = [
            f"How do you currently handle tasks related to {prompt}, and what is the most frustrating part of that process?",
            f"What other tools, services, or manual workarounds have you tried, and why did they fall short?",
            f"If an automated solution solved this completely for you, how would that change your daily or weekly workflow?",
            f"When considering a solution like this at {pricing}, what would make it an immediate yes vs an easy pass?",
            "What potential concerns or hesitations would you have before trusting this in your daily routine?",
        ]

    study.script_questions = generated_questions
    study.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "study_id": study_id,
        "questions": generated_questions,
        "count": len(generated_questions),
        "source": "fallback_static" if fallback_reason else "llm",
        "fallback_reason": fallback_reason,
    }


# ============================================================================
# Autonomous Research Trigger & Status
# ============================================================================

@router.post("/studies/{study_id}/research/run")
@limiter.limit("20/minute")
async def trigger_study_research(
    study_id: str,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger autonomous research and dataset discovery for a study in background."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: a research run writes evidence rows and spends LLM budget.
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    research_engine = getattr(request.app.state, "research_engine", None) if request else None
    if not research_engine:
        # Fallback inline engine if not registered
        llm_service = getattr(request.app.state, "llm_service", None) if request else None
        vector_engine = getattr(request.app.state, "vector_engine", None) if request else None
        research_engine = ResearchEngineService(llm_service=llm_service, vector_engine=vector_engine)

    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID
    run = await research_engine.run_study_research(
        session=session,
        study=study,
        user_id=effective_user_id,
    )

    return {
        "run_id": run.id,
        "study_id": study_id,
        "status": run.status,
        "source_count": run.source_count,
        "claim_count": run.claim_count,
        "dataset_candidate_count": run.dataset_candidate_count,
    }


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
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

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
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

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
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

    report = await session.get(StudyReports, report_id)
    if not report or report.study_id != study_id:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found for study '{study_id}'")
    return _serialize_report(report)


@router.post("/studies/{study_id}/reports/generate", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def generate_study_report(
    study_id: str,
    payload: Optional[GenerateReportRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Synthesize and persist a comprehensive research report for the study."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: this persists a StudyReports row and spends LLM budget.
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    llm_service = getattr(request.app.state, "llm_service", None) if request else None
    report_service = StudyReportService(session=session, llm_service=llm_service)

    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID
    custom_title = payload.title if payload else None

    report = await report_service.generate_report(
        study_id=study_id,
        user_id=effective_user_id,
        custom_title=custom_title,
    )

    return _serialize_report(report)


# ---------------------------------------------------------------------------
# Async report-generation jobs: synthesis reads every interview and runs LLM
# calls on a 150 s task budget — beyond comfortable HTTP timeouts. POST
# starts a background job (202), the UI polls; the report row is persisted
# by the service, only job STATUS is in-memory.
# ---------------------------------------------------------------------------

@router.post("/studies/{study_id}/reports/generate/jobs", status_code=202)
@limiter.limit("10/minute")
async def start_report_generation_job(
    study_id: str,
    payload: Optional[GenerateReportRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start report synthesis in the background; poll the job endpoint."""
    study = await session.get(Studies, study_id)
    # 404-first write gate: the job persists a StudyReports row and spends LLM budget.
    require_study_access(
        study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found"
    )

    app = request.app
    sessionmaker_ = getattr(app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    llm_service = getattr(app.state, "llm_service", None)
    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID
    custom_title = payload.title if payload else None

    async def _runner(job: dict[str, Any]) -> None:
        # The request session is gone by now — the job owns its own session.
        async with sessionmaker_() as job_session:
            report_service = StudyReportService(session=job_session, llm_service=llm_service)
            report = await report_service.generate_report(
                study_id=study_id,
                user_id=effective_user_id,
                custom_title=custom_title,
            )
            job["result"] = _serialize_report(report)

    job = start_job(
        app,
        kind="report_generation",
        scope_id=study_id,
        runner=_runner,
        user_id=effective_user_id,
        # Honest domain failures (R2/R6) pass their message through.
        user_safe_exceptions=(ContextWindowExceeded, AllCandidatesFailed),
    )
    return {"job_id": job["job_id"], "study_id": study_id, "status": job["status"]}


@router.get("/studies/{study_id}/reports/generate/jobs/{job_id}")
async def get_report_generation_job(
    study_id: str,
    job_id: str,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Poll a report-generation job. 404 for unknown/lost jobs (e.g. restart)."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")
    job = get_job(request.app, job_id, kind="report_generation", scope_id=study_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail="job not found (it may have been lost in a server restart)",
        )
    return job
