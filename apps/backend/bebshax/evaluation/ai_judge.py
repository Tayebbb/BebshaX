"""AI judge: an independent model pass that REVIEWS what the platform produced.

RULES.md R2/R3: every artefact BebshaX shows is written by a model from the
study's own inputs. This module closes the loop by asking a model (routed as
``TaskType.CRITIC``) to audit those artefacts against a fixed rubric and say —
with citations into the material — whether they are grounded, specific to the
study, internally consistent and honest about their limits. The judge never
rewrites artefacts; it only scores and explains. No template verdict exists:
without an LLM or with an unusable reply the review fails explicitly.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import EvidenceClaims, MarketSegments, Personas, Studies, StudyReports
from bebshax.interview.orm import Conversations
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.placeholders import is_placeholder
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_json_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.utils.explicit_failures import InsufficientInput, LLMUnavailable, UnusableModelOutput

logger = logging.getLogger(__name__)

JUDGE_UNAVAILABLE = "judge_unavailable"
JUDGE_NOTHING_TO_REVIEW = "nothing_to_review"
_MAX_ATTEMPTS = 2
# Artefacts that make a study reviewable. A report is derived from these; a
# report row over an otherwise empty study is not material to score.
PRIMARY_ARTEFACTS: tuple[str, ...] = ("personas", "segments", "evidence_claims", "interviews")

# Rubric (data table): dimension -> what the judge must check. Extend the table.
RUBRIC: dict[str, str] = {
    "grounding": "Every figure, behaviour or claim traces to the study brief, the evidence claims, the dataset or the transcript — nothing is asserted that no input supports.",
    "specificity": "The artefacts are unmistakably about THIS idea, audience and market; they would be wrong for a different study (no generic personas, no boilerplate findings).",
    "consistency": "Personas, interview answers, segments and the report agree with each other (budgets, roles, needs, geography, currency).",
    "honesty": "Limits are stated: missing evidence is called missing, synthetic signals are labelled synthetic, no invented precision.",
    "actionability": "A founder could act on the findings: concrete pain points, willingness-to-pay signals, risks and next steps.",
}


class JudgeIssue(BaseModel):
    severity: str = "medium"  # high | medium | low
    artifact: str = ""  # persona:<id> | report | interview:<id> | segment:<id> | evidence
    detail: str


class JudgeVerdict(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    dimension_scores: dict[str, int] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    issues: list[JudgeIssue] = Field(default_factory=list)
    verdict: str
    scope: str  # "study" | "persona"
    reviewed_artifacts: dict[str, int] = Field(default_factory=dict)
    served_by: Optional[str] = None
    llm_request_id: Optional[str] = None
    attempts: int = 1
    reviewed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _persona_view(p: Personas) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "archetype": p.archetype,
        "segment_id": p.segment_id,
        "bio": p.bio,
        "demographics": p.demographics or {},
        "commercial_profile": p.commercial_profile or {},
        "goals": (p.goals or [])[:4],
        "pain_points": (p.pain_points or [])[:4],
        "objections": (p.objections or [])[:3],
        "behaviors": (p.behaviors or [])[:4],
        "grounding_score": p.grounding_score,
        "generation_model": p.generation_model,
    }


async def gather_study_material(session: AsyncSession, study: Studies, *, persona_ids: Optional[list[str]] = None) -> dict[str, Any]:
    """Everything the judge may look at, straight from the study's rows."""
    persona_q = select(Personas).where(Personas.study_id == study.id, Personas.status != "archived")
    if persona_ids:
        persona_q = persona_q.where(Personas.id.in_(persona_ids))
    personas = list((await session.execute(persona_q)).scalars())
    claims = list((await session.execute(select(EvidenceClaims).where(EvidenceClaims.study_id == study.id))).scalars())
    segments = list((await session.execute(select(MarketSegments).where(MarketSegments.study_id == study.id))).scalars())
    conversations = list(
        (await session.execute(select(Conversations).where(Conversations.study_id == study.id).order_by(Conversations.created_at.desc()).limit(8))).scalars()
    )
    report = (
        await session.execute(select(StudyReports).where(StudyReports.study_id == study.id).order_by(StudyReports.version.desc()).limit(1))
    ).scalar_one_or_none()

    return {
        "study": {
            "id": study.id,
            "title": study.title,
            "idea": study.prompt,
            "goal": study.goal,
            "target_audience": study.target_audience,
            "pricing_hypothesis": study.pricing_hypothesis,
            "script_questions": (study.script_questions or [])[:12],
        },
        "personas": [_persona_view(p) for p in personas[:12]],
        "segments": [
            {"id": s.id, "name": s.name, "description": s.description, "share_pct": s.population_percentage, "status": s.status}
            for s in segments[:8]
        ],
        "evidence_claims": [
            {"id": c.id, "text": c.claim_text, "status": c.status, "category": c.category, "confidence": c.confidence, "sources": len(c.supporting_source_ids or [])}
            for c in claims[:15]
        ],
        "interviews": [
            {
                "id": c.id,
                "persona_id": c.persona_id,
                "status": c.status,
                "summary": c.summary,
                "key_findings": (c.key_findings or [])[:5],
            }
            for c in conversations
        ],
        "report": None
        if report is None
        else {
            "version": report.version,
            "executive_summary": report.executive_summary,
            "key_findings": (report.key_findings or [])[:8],
            "recommendations": (report.recommendations or [])[:6],
            "limitations": report.limitations,
            "metrics": report.metrics,
        },
    }


def _counts(material: dict[str, Any]) -> dict[str, int]:
    return {
        "personas": len(material["personas"]),
        "segments": len(material["segments"]),
        "evidence_claims": len(material["evidence_claims"]),
        "interviews": len(material["interviews"]),
        "reports": 1 if material["report"] else 0,
    }


def _numeric(value: Any) -> Optional[float]:
    """The number a score field holds (int, float or numeric string), else None.
    Bools and non-finite values are not scores. Observed live: a 3B route
    returned non-numeric dimensions and a default of 0 turned them into an
    all-zero verdict the model never gave — absence, not zero (R2)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


async def _ask_judge(llm: LLMService, scope: str, system_prompt: str, material: dict[str, Any]) -> JudgeVerdict:
    request = LLMRequest(
        task=TaskType.CRITIC,
        messages=[
            ChatMessage(role="system", content=system_prompt + "\n" + UNTRUSTED_RULE),
            ChatMessage(role="user", content=untrusted_json_block("MATERIAL_UNDER_REVIEW", material, source="study records")),
        ],
        json_mode=True,
        temperature=0.2,
        max_output_tokens=1400,
    )
    served_by = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            request = request.retry_copy()
        result = await llm.complete(request)  # LLMError propagates (503 envelope)
        served_by = f"{result.provider}/{result.model}"
        try:
            parsed = parse_llm_json(result.text)
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict) or not str(parsed.get("verdict") or "").strip():
            logger.warning("AI judge reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue
        overall = _numeric(parsed.get("overall_score"))
        if overall is None:
            # No score is no verdict: never invent 0 for a missing/non-numeric one.
            logger.warning("AI judge reply has no numeric overall_score (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue
        raw_dims = parsed.get("dimension_scores") if isinstance(parsed.get("dimension_scores"), dict) else {}
        dimension_scores = {
            dim: _clamp_score(score)
            for dim in RUBRIC
            if (score := _numeric(raw_dims.get(dim))) is not None  # non-numeric -> omitted, not 0
        }
        issues = []
        for item in parsed.get("issues") or []:
            if isinstance(item, dict) and str(item.get("detail") or "").strip():
                sev = str(item.get("severity") or "medium").lower()
                artifact = str(item.get("artifact") or "")
                if is_placeholder(artifact):
                    artifact = ""  # the schema's own "persona:<id>" slot, not a reference
                issues.append(JudgeIssue(severity=sev if sev in ("high", "medium", "low") else "medium", artifact=artifact, detail=str(item["detail"]).strip()))
            elif isinstance(item, str) and item.strip():
                issues.append(JudgeIssue(detail=item.strip()))
        return JudgeVerdict(
            overall_score=_clamp_score(overall),
            dimension_scores=dimension_scores,
            strengths=[str(s).strip() for s in (parsed.get("strengths") or []) if str(s).strip()][:8],
            issues=issues[:12],
            verdict=str(parsed["verdict"]).strip(),
            scope=scope,
            reviewed_artifacts=_counts(material) if scope == "study" else {"personas": len(material.get("personas", []))},
            served_by=served_by,
            llm_request_id=request.request_id,
            attempts=attempt,
        )
    raise UnusableModelOutput(
        JUDGE_UNAVAILABLE,
        f"The reviewing model's reply could not be used after {_MAX_ATTEMPTS} attempts; no verdict was invented.",
        attempts=_MAX_ATTEMPTS,
        served_by=served_by,
    )


def _rubric_text() -> str:
    return "\n".join(f"- {dim}: {desc}" for dim, desc in RUBRIC.items())


_OUTPUT_SCHEMA = (
    'Output ONLY JSON: {"overall_score": 0-100, "dimension_scores": {"grounding": 0-100, "specificity": 0-100, '
    '"consistency": 0-100, "honesty": 0-100, "actionability": 0-100}, "strengths": ["..."], '
    '"issues": [{"severity": "high|medium|low", "artifact": "persona:<id>|report|interview:<id>|segment:<id>|evidence", "detail": "..."}], '
    '"verdict": "2-4 sentences"}'
)


async def judge_study(session: AsyncSession, study: Studies, llm: Optional[LLMService]) -> JudgeVerdict:
    """Independent review of everything the study has produced so far."""
    if llm is None:
        raise LLMUnavailable("AI review")
    material = await gather_study_material(session, study)
    counts = _counts(material)
    if not any(counts[key] for key in PRIMARY_ARTEFACTS):
        raise InsufficientInput(
            JUDGE_NOTHING_TO_REVIEW,
            "This study has no personas, evidence, interviews or segments yet — a report alone is not "
            "reviewable. Run the pipeline first, then ask for an AI review.",
        )
    system_prompt = (
        "You are an independent research auditor reviewing the outputs of a synthetic customer-research platform. "
        "You did NOT write these artefacts. Score them strictly against the rubric, citing the artefact ids you refer to. "
        "Generic content that would fit any product, figures no input supports, or contradictions between artefacts must "
        "lower the score. Say plainly what is missing (e.g. no evidence claims, no interviews). Do not rewrite anything.\n"
        f"RUBRIC:\n{_rubric_text()}\n{_OUTPUT_SCHEMA}"
    )
    return await _ask_judge(llm, "study", system_prompt, material)


async def judge_persona(session: AsyncSession, study: Studies, persona: Personas, llm: Optional[LLMService]) -> JudgeVerdict:
    """Independent review of one persona against its study."""
    if llm is None:
        raise LLMUnavailable("AI review")
    material = await gather_study_material(session, study, persona_ids=[persona.id])
    material = {
        "study": material["study"],
        "personas": material["personas"],
        "segments": [s for s in material["segments"] if s["id"] == persona.segment_id] or material["segments"][:3],
        "evidence_claims": material["evidence_claims"][:8],
    }
    if not material["personas"]:
        raise InsufficientInput(JUDGE_NOTHING_TO_REVIEW, "This persona is archived or belongs to another study.")
    system_prompt = (
        "You are an independent research auditor reviewing ONE synthetic persona against the study it was generated for. "
        "You did NOT write it. Judge whether it is specific to this idea/audience/market, internally coherent (age, role, "
        "income, budget, currency, behaviours), grounded in the segment and evidence shown, and honest about unknowns. "
        "A persona that would fit any product, or that states figures nothing supports, must score low. Cite fields.\n"
        f"RUBRIC:\n{_rubric_text()}\n{_OUTPUT_SCHEMA}"
    )
    return await _ask_judge(llm, "persona", system_prompt, material)
