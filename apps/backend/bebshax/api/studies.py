"""FastAPI routes for research studies and persona library audience persistence."""

from datetime import datetime, timezone
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.api.auth import get_optional_current_user
from bebshax.api.jobs import get_job, start_job
from bebshax.db.models import Studies, SavedAudiences, StudyReports
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.tenancy import PUBLIC_OWNER_IDS as _PUBLIC_OWNER_IDS
from bebshax.tenancy import STUDY_ANON_OWNER_IDS as _STUDY_ANON_OWNER_IDS
from bebshax.tenancy import owner_accessible as _tenancy_owner_accessible
from bebshax.utils.title_generator import generate_deterministic_study_title
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.report_service import StudyReportService

router = APIRouter(tags=["studies"])


class StudyCreateRequest(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    title: Optional[str] = None
    type: str = "interviews"
    study_type: Optional[str] = None
    goal: str = "demand_validation"
    prompt: Optional[str] = None
    product_idea: Optional[str] = None
    target_audience: Optional[str] = None
    pricing_hypothesis: Optional[str] = None
    status: str = "draft"
    step: int = 1
    persona_count: int = 0
    persona_ids: list[str] = Field(default_factory=list)
    suggested_roles: list[dict[str, Any]] = Field(default_factory=list)
    script_questions: list[str] = Field(default_factory=list)
    findings: Optional[dict[str, Any]] = None
    is_demo: bool = False
    duration_text: Optional[str] = None
    copilot_messages: Optional[list[dict[str, Any]]] = None
    personas_data: Optional[list[dict[str, Any]]] = None


class StudyUpdateRequest(BaseModel):
    user_id: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None
    study_type: Optional[str] = None
    goal: Optional[str] = None
    prompt: Optional[str] = None
    product_idea: Optional[str] = None
    target_audience: Optional[str] = None
    pricing_hypothesis: Optional[str] = None
    status: Optional[str] = None
    step: Optional[int] = None
    persona_count: Optional[int] = None
    persona_ids: Optional[list[str]] = None
    suggested_roles: Optional[list[dict[str, Any]]] = None
    script_questions: Optional[list[str]] = None
    findings: Optional[dict[str, Any]] = None
    is_demo: Optional[bool] = None
    duration_text: Optional[str] = None
    copilot_messages: Optional[list[dict[str, Any]]] = None
    personas_data: Optional[list[dict[str, Any]]] = None


class AudienceCreateRequest(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    study_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    persona_ids: list[str] = Field(default_factory=list)
    personas_payload: list[dict[str, Any]] = Field(default_factory=list)
    role_distribution: dict[str, Any] = Field(default_factory=dict)


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


def _user_owns_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Return True if the current user owns the study, or it is a public demo / default study."""
    if study.is_demo:
        return True
    if current_user and study.user_id == current_user.id:
        return True
    if current_user is None and (not study.user_id or study.user_id in _STUDY_ANON_OWNER_IDS):
        return True
    return False


def _owner_accessible(owner_id: Optional[str], current_user: Optional[Users]) -> bool:
    """Row-level access rule for owner-stamped rows (audiences, businesses,
    personas, conversations): shared/system rows are readable by every caller;
    owned rows require the owner's token. NOTE the deliberate delta from
    `_user_owns_study`: studies use the `is_demo` flag and do not grant
    authenticated users the anonymous tenant — see bebshax/tenancy.py."""
    return _tenancy_owner_accessible(owner_id, current_user.id if current_user else None)


async def get_session(request: Request) -> AsyncSession:
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None)
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        yield session


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
async def create_study(
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

    study_id = payload.id or f"study_{uuid.uuid4().hex[:16]}"
    # Identity comes from the token only — payload.user_id would let any
    # caller attach rows to another tenant (spoofing).
    study_user_id = current_user.id if current_user else "usr_default"

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
        is_demo=payload.is_demo,
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
    Returns 403 if the study exists but belongs to a different user.
    """
    study = await session.get(Studies, study_id)
    if not study:
        # Auto-create — supports seamless workflow initialization.
        # Identity from the token only (never payload.user_id — spoofing).
        study_user_id = current_user.id if current_user else "usr_default"
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
        # Ownership guard: return 403 Forbidden when trying to update another user's study
        if not _user_owns_study(study, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this study",
            )
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
    # re-attach the study to an arbitrary tenant (spoofing).
    update_data.pop("id", None)
    update_data.pop("user_id", None)

    for field, val in update_data.items():
        if val is not None and hasattr(study, field):
            setattr(study, field, val)

    study.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(study)
    return _serialize_study(study)


@router.delete("/studies/{study_id}")
async def delete_study(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delete a research study and all dependent records. Returns 403 if not owned by caller, 404 if not found."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this study",
        )
    # Cascade cleanup of dependent study records
    from sqlalchemy import delete
    from bebshax.db.models import DatasetCandidates, DatasetSources, EvidenceClaims, EvidenceChunks, EvidenceSources, ResearchPlans, ResearchRuns

    await session.execute(delete(ResearchPlans).where(ResearchPlans.study_id == study_id))
    await session.execute(delete(DatasetCandidates).where(DatasetCandidates.study_id == study_id))
    await session.execute(delete(EvidenceClaims).where(EvidenceClaims.study_id == study_id))
    await session.execute(delete(EvidenceChunks).where(EvidenceChunks.study_id == study_id))
    await session.execute(delete(EvidenceSources).where(EvidenceSources.study_id == study_id))
    await session.execute(delete(ResearchRuns).where(ResearchRuns.study_id == study_id))
    await session.execute(delete(DatasetSources).where(DatasetSources.study_id == study_id))
    await session.execute(delete(SavedAudiences).where(SavedAudiences.study_id == study_id))

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
    audience_id = payload.id or f"aud_{uuid.uuid4().hex[:16]}"
    # Identity from the token only (never payload.user_id — spoofing).
    aud_user_id = current_user.id if current_user else "usr_default"
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
    if not _owner_accessible(audience.user_id, current_user):
        # 404 (not 403) — do not confirm the row exists to non-owners.
        raise HTTPException(status_code=404, detail=f"Audience '{audience_id}' not found")
    await session.delete(audience)
    await session.commit()
    return {"success": True, "deleted_id": audience_id}


# ============================================================================
# Dynamic Script Questions Generation
# ============================================================================

@router.post("/studies/{study_id}/script/generate")
async def generate_script_questions(
    study_id: str,
    payload: Optional[GenerateScriptRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate dynamic, context-specific interview script questions for a study."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

    prompt = (payload and payload.prompt) or study.prompt or study.title or "Business Idea"
    target_aud = study.target_audience or "Target User"
    pricing = study.pricing_hypothesis or "Market Pricing"
    q_count = (payload and payload.question_count) or 5

    llm_service = getattr(request.app.state, "llm_service", None) if request else None

    generated_questions = []
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
            import json, re
            cleaned = res.text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, list) and len(parsed) >= 2:
                generated_questions = [str(q).strip() for q in parsed if str(q).strip()]
            elif isinstance(parsed, dict) and "questions" in parsed and isinstance(parsed["questions"], list):
                generated_questions = [str(q).strip() for q in parsed["questions"] if str(q).strip()]
        except Exception:
            pass

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
    }


# ============================================================================
# Autonomous Research Trigger & Status
# ============================================================================

@router.post("/studies/{study_id}/research/run")
async def trigger_study_research(
    study_id: str,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trigger autonomous research and dataset discovery for a study in background."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

    research_engine = getattr(request.app.state, "research_engine", None) if request else None
    if not research_engine:
        # Fallback inline engine if not registered
        from bebshax.research.service import ResearchEngineService
        llm_service = getattr(request.app.state, "llm_service", None) if request else None
        vector_engine = getattr(request.app.state, "vector_engine", None) if request else None
        research_engine = ResearchEngineService(llm_service=llm_service, vector_engine=vector_engine)

    effective_user_id = (current_user.id if current_user else None) or study.user_id or "usr_default"
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
async def generate_study_report(
    study_id: str,
    payload: Optional[GenerateReportRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Synthesize and persist a comprehensive research report for the study."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

    llm_service = getattr(request.app.state, "llm_service", None) if request else None
    report_service = StudyReportService(session=session, llm_service=llm_service)

    effective_user_id = (current_user.id if current_user else None) or study.user_id or "usr_default"
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
async def start_report_generation_job(
    study_id: str,
    payload: Optional[GenerateReportRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start report synthesis in the background; poll the job endpoint."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(status_code=403, detail="Not authorized for this study")

    app = request.app
    sessionmaker_ = getattr(app.state, "db_sessionmaker", None)
    if sessionmaker_ is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    llm_service = getattr(app.state, "llm_service", None)
    effective_user_id = (current_user.id if current_user else None) or study.user_id or "usr_default"
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
