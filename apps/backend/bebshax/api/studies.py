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
from bebshax.db.models import Studies, SavedAudiences
from bebshax.utils.title_generator import generate_deterministic_study_title

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


def _user_owns_study(study: Studies, current_user: Optional[Users]) -> bool:
    """Return True if the current user owns the study, or it is a public demo / default study."""
    if study.is_demo:
        return True
    if current_user and study.user_id == current_user.id:
        return True
    if current_user is None and (not study.user_id or study.user_id in ("usr_default", "anonymous")):
        return True
    return False


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

    If no authenticated user can be resolved, returns [] (never all studies).
    """
    effective_user_id = (current_user.id if current_user else None) or user_id
    if effective_user_id:
        stmt = select(Studies).where(
            or_(Studies.user_id == effective_user_id, Studies.is_demo == True)
        ).order_by(Studies.created_at.desc())
    else:
        # Unauthenticated — return only public demo studies (never leak all studies)
        stmt = select(Studies).where(Studies.is_demo == True).order_by(Studies.created_at.desc())
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
    study_user_id = (current_user.id if current_user else None) or payload.user_id or "usr_default"

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
        # Auto-create — supports seamless workflow initialization
        study_user_id = (current_user.id if current_user else None) or payload.user_id or "usr_default"
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
        # Backfill user_id if it was missing (e.g. created anonymously, now logged in)
        if current_user and not study.user_id:
            study.user_id = current_user.id
        elif payload.user_id and not study.user_id:
            study.user_id = payload.user_id

    update_data = payload.model_dump(exclude_unset=True)
    if "product_idea" in update_data and "prompt" not in update_data:
        update_data["prompt"] = update_data["product_idea"]
    if "study_type" in update_data and "type" not in update_data:
        update_data["type"] = update_data["study_type"]

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
    """List all saved audiences in the persona library for the user."""
    effective_user_id = (current_user.id if current_user else None) or user_id
    if effective_user_id:
        stmt = select(SavedAudiences).where(
            or_(SavedAudiences.user_id == effective_user_id, SavedAudiences.user_id == None)
        ).order_by(SavedAudiences.created_at.desc())
    else:
        stmt = select(SavedAudiences).order_by(SavedAudiences.created_at.desc())
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
    aud_user_id = (current_user.id if current_user else None) or payload.user_id or "usr_default"
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
    await session.delete(audience)
    await session.commit()
    return {"success": True, "deleted_id": audience_id}
