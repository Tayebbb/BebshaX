"""AI review endpoints: an independent model audits a study's artefacts.

``POST /api/studies/{study_id}/ai-review`` and
``POST /api/studies/{study_id}/personas/{persona_id}/ai-review`` return a
rubric-scored verdict written by the reviewing model (``TaskType.CRITIC``), with
the route that served it. Both spend model budget, so they use the study write
gate; failures surface as coded envelopes (llm_unavailable, judge_unavailable,
nothing_to_review) — never a canned verdict.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.deps import get_session, require_study_access
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.evaluation.ai_judge import RUBRIC, judge_persona, judge_study

router = APIRouter(tags=["ai-review"])


@router.get("/ai-review/rubric")
async def get_ai_review_rubric() -> dict[str, Any]:
    """The fixed rubric the reviewing model scores against (transparency for judges)."""
    return {"dimensions": RUBRIC, "scale": "0-100 per dimension and overall"}


@router.post("/studies/{study_id}/ai-review")
@limiter.limit("6/minute")
async def review_study(
    study_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Independent AI review of everything the study has produced so far."""
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found")
    llm = getattr(request.app.state, "llm_service", None)
    verdict = await judge_study(session, study, llm)
    return {"study_id": study_id, **verdict.model_dump()}


@router.post("/studies/{study_id}/personas/{persona_id}/ai-review")
@limiter.limit("12/minute")
async def review_persona(
    study_id: str,
    persona_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Independent AI review of one persona against its study."""
    study = await session.get(Studies, study_id)
    require_study_access(study, current_user, write=True, not_found_detail=f"Study '{study_id}' not found")
    persona = await session.get(Personas, persona_id)
    if persona is None or persona.study_id != study_id:
        raise HTTPException(status_code=404, detail="Persona not found in this study")
    llm = getattr(request.app.state, "llm_service", None)
    verdict = await judge_persona(session, study, persona, llm)
    return {"study_id": study_id, "persona_id": persona_id, **verdict.model_dump()}
