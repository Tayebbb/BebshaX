"""Interview REST API: study-scoped adaptive persona interviews, transcript streaming, and insight synthesis."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import aclosing
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.deps import (
    get_session,
    owner_accessible,
    owner_can_write,
    user_can_write_study,
    user_owns_study,
)
from bebshax.api.errors import APIError, request_id_of
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.engine import ConversationNotFound, InterviewEngine, InterviewFinished, PersonaNotFound
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.utils.explicit_failures import LLMUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interviews"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class StartInterviewRequest(BaseModel):
    persona_id: Optional[str] = None
    objective: str = Field(min_length=1, max_length=2000)
    custom_objective: Optional[str] = Field(default=None, max_length=2000)
    length_tier: str = Field(default="standard", pattern="^(short|standard|deep)$")


class InterviewMessageRequest(BaseModel):
    message: Optional[str] = Field(default=None, max_length=8000)
    content: Optional[str] = Field(default=None, max_length=8000)


class BatchInterviewRunRequest(BaseModel):
    # Caps bound real LLM spend: N personas × M questions of sequential calls.
    persona_ids: Optional[list[str]] = Field(default=None, max_length=50)
    questions: Optional[list[str]] = Field(default=None, max_length=20)

    @field_validator("questions")
    @classmethod
    def question_length(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v and any(len(q) > 2000 for q in v):
            raise ValueError("each question must be ≤2000 characters")
        return v


# Backward compatibility
class ConversationCreate(BaseModel):
    persona_id: Optional[str] = None
    objective: str = Field(min_length=1, max_length=2000)


class MessageIn(BaseModel):
    message: Optional[str] = Field(default=None, max_length=8000)
    content: Optional[str] = Field(default=None, max_length=8000)


# ---------------------------------------------------------------------------
# Helper Serializers
# ---------------------------------------------------------------------------

def _serialize_turn(t: ConversationTurns) -> dict[str, Any]:
    meta = t.metadata_json or {}
    return {
        "id": t.id,
        "interview_id": t.conversation_id,
        "conversation_id": t.conversation_id,
        "turn_number": t.turn_number,
        "role": t.role,
        "content": t.content,
        "topic": t.topic,
        "latency_ms": t.latency_ms,
        "served_by": t.served_by,
        "retrieved_memories": t.retrieved_memories or [],
        "metadata": meta,
        # Lifted from metadata so reloaded transcripts flag turns like live ones.
        "identity_drift": bool(meta.get("identity_drift", False)),
        "drift_notes": meta.get("drift_notes") or [],
        "contradiction_detected": bool(meta.get("contradiction_detected", False)),
        "contradiction_details": meta.get("contradiction_details"),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _serialize_insight(i: InterviewInsights) -> dict[str, Any]:
    return {
        "id": i.id,
        "interview_id": i.interview_id,
        "study_id": i.study_id,
        "persona_id": i.persona_id,
        "type": i.type,
        "title": i.title,
        "description": i.description,
        "supporting_turn_numbers": i.supporting_turn_numbers or [],
        "confidence": i.confidence,
        "is_synthetic": i.is_synthetic,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _serialize_interview(
    c: Conversations,
    persona: Optional[Personas] = None,
    turns: Optional[list[ConversationTurns]] = None,
    insights: Optional[list[InterviewInsights]] = None,
) -> dict[str, Any]:
    return {
        "id": c.id,
        "study_id": c.study_id,
        "user_id": c.user_id,
        "persona_id": c.persona_id,
        "persona_name": persona.name if persona else "Synthetic Persona",
        "persona_avatar": persona.name.split(" ")[0] if persona else "P",
        "persona_version": c.persona_version,
        "persona_demographics": persona.demographics if persona else {},
        "persona_segment_id": persona.segment_id if persona else None,
        "generation_run_id": c.generation_run_id,
        "objective": c.objective,
        "custom_objective": c.custom_objective,
        "interview_type": c.interview_type,
        "length_tier": c.length_tier,
        "max_turns": c.max_turns,
        "status": c.status,
        "topics_explored": c.topics_explored or {},
        "question_count": c.question_count,
        "turn_count": c.turn_count,
        "summary": c.summary,
        "key_findings": c.key_findings or [],
        "structured_insights": (
            [_serialize_insight(i) for i in insights]
            if insights is not None
            else (c.structured_insights or [])
        ),
        "turns": [_serialize_turn(t) for t in (turns or [])],
        "configuration": c.configuration or {},
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "completed_at": c.completed_at.isoformat() if c.completed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def _get_study_and_verify_access(
    session: AsyncSession, study_id: str, current_user: Optional[Users], *, write: bool = False
) -> Studies:
    """``write=True`` selects the strict write predicate: the ``is_demo`` read
    allowance must never let a non-owner mutate the shared demo."""
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study not found")
    predicate = user_can_write_study if write else user_owns_study
    if not predicate(study, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this study"
        )
    return study


def _require_interview_in_study(
    conversation: Optional[Conversations],
    study_id: str,
    current_user: Optional[Users],
    *,
    write: bool = False,
) -> Conversations:
    """Scope an interview row to its study.

    The parent comparison is UNCONDITIONAL. It used to be guarded by
    ``conversation.study_id and ...``, so a row with a NULL/empty ``study_id``
    skipped the check entirely and was accepted under *any* study id.

    ``write=True`` additionally applies the strict write predicate to the row's
    own tenant stamp, mirroring ``_guard_legacy_conversation``.
    """
    if not conversation:
        raise HTTPException(status_code=404, detail="Interview not found")
    if conversation.study_id != study_id:
        raise HTTPException(status_code=403, detail="Interview does not belong to this study")
    if write and not owner_can_write(conversation.user_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to modify this interview")
    return conversation


# ============================================================================
# Study-Scoped Interview Endpoints
# ============================================================================

@router.post("/studies/{study_id}/personas/{persona_id}/interviews", status_code=201)
async def start_study_persona_interview(
    study_id: str,
    persona_id: str,
    body: StartInterviewRequest,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start an adaptive persona interview under a study with strict ownership validation."""
    await _get_study_and_verify_access(session, study_id, current_user, write=True)

    persona = await session.get(Personas, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    # Unconditional: a NULL study_id must not read as "belongs to every study".
    if persona.study_id != study_id:
        raise HTTPException(status_code=403, detail="Persona does not belong to this study")
    if not owner_can_write(persona.owner_id, current_user):
        raise HTTPException(status_code=403, detail="Not authorized to interview this persona")

    user_id = current_user.id if current_user else None
    try:
        conversation = await request.app.state.interview_engine.start(
            persona_id=persona_id,
            objective=body.objective,
            study_id=study_id,
            user_id=user_id,
            custom_objective=body.custom_objective,
            length_tier=body.length_tier,
        )
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc

    return _serialize_interview(conversation, persona, turns=[])


@router.get("/studies/{study_id}/interviews")
async def list_study_interviews(
    study_id: str,
    persona_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    objective: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all interviews conducted in this study with filtering and search."""
    await _get_study_and_verify_access(session, study_id, current_user)

    stmt = select(Conversations).where(Conversations.study_id == study_id)
    if persona_id:
        stmt = stmt.where(Conversations.persona_id == persona_id)
    if status and status != "all":
        stmt = stmt.where(Conversations.status == status)
    if objective and objective != "all":
        stmt = stmt.where(Conversations.objective == objective)

    stmt = stmt.order_by(Conversations.created_at.desc())
    conv_list = list((await session.execute(stmt)).scalars())

    # Bulk fetch personas
    persona_ids = list(set(c.persona_id for c in conv_list))
    personas_map: dict[str, Personas] = {}
    if persona_ids:
        p_stmt = select(Personas).where(Personas.id.in_(persona_ids))
        for p in (await session.execute(p_stmt)).scalars():
            personas_map[p.id] = p

    # Filter search query on persona name or objective/summary if provided
    items = []
    for c in conv_list:
        p = personas_map.get(c.persona_id)
        if search:
            q = search.lower()
            match_name = p.name.lower() if p else ""
            match_obj = c.objective.lower()
            match_custom = (c.custom_objective or "").lower()
            match_sum = (c.summary or "").lower()
            if not (q in match_name or q in match_obj or q in match_custom or q in match_sum):
                continue
        items.append(_serialize_interview(c, p))

    return {
        "study_id": study_id,
        "total": len(items),
        "interviews": items,
    }


@router.get("/studies/{study_id}/interviews/metrics")
async def get_study_interview_metrics(
    study_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate metric counts for study interviews."""
    await _get_study_and_verify_access(session, study_id, current_user)

    agg_stmt = select(
        func.count().label("total"),
        func.sum(case((Conversations.status == "active", 1), else_=0)).label("active"),
        func.sum(case((Conversations.status == "completed", 1), else_=0)).label("completed"),
    ).where(Conversations.study_id == study_id)
    row = (await session.execute(agg_stmt)).one()
    total = row.total or 0
    active = row.active or 0
    completed = row.completed or 0

    insights_count = (
        await session.execute(
            select(func.count()).select_from(InterviewInsights).where(
                InterviewInsights.study_id == study_id
            )
        )
    ).scalar() or 0

    return {
        "study_id": study_id,
        "total_interviews": total,
        "active_interviews": active,
        "completed_interviews": completed,
        "total_insights_generated": insights_count,
    }


@router.get("/studies/{study_id}/interviews/{interview_id}")
async def get_study_interview_detail(
    study_id: str,
    interview_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full interview detail including transcript, topics, and structured insights."""
    await _get_study_and_verify_access(session, study_id, current_user)

    conversation = _require_interview_in_study(
        await session.get(Conversations, interview_id), study_id, current_user
    )

    persona = await session.get(Personas, conversation.persona_id)

    # Fetch turns
    turns_stmt = (
        select(ConversationTurns)
        .where(ConversationTurns.conversation_id == interview_id)
        .order_by(ConversationTurns.turn_number)
    )
    turns = list((await session.execute(turns_stmt)).scalars())

    # Fetch insights
    ins_stmt = (
        select(InterviewInsights)
        .where(InterviewInsights.interview_id == interview_id)
        .order_by(InterviewInsights.created_at.desc())
    )
    insights = list((await session.execute(ins_stmt)).scalars())

    # Suggested follow-ups, written by the model from this transcript (empty when unavailable).
    suggested = await request.app.state.interview_engine.generate_suggested_questions(
        conversation, persona, turns
    )

    data = _serialize_interview(conversation, persona, turns, insights)
    data["suggested_questions"] = suggested
    return data


@router.post("/studies/{study_id}/interviews/{interview_id}/messages")
@limiter.limit("30/minute")
async def post_study_interview_message(
    study_id: str,
    interview_id: str,
    body: InterviewMessageRequest,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit a researcher question and receive the adaptive persona response.

    ContextWindowExceeded (413) and AllCandidatesFailed (503) propagate to the
    global handlers in api/errors.py, which render the rich envelope (attempts,
    failure kinds, llm_request_id) — a local ``except`` would flatten it.
    """
    await _get_study_and_verify_access(session, study_id, current_user, write=True)

    _require_interview_in_study(
        await session.get(Conversations, interview_id), study_id, current_user, write=True
    )

    text = body.content or body.message
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        result = await request.app.state.interview_engine.ask(interview_id, text.strip())
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="Persona not found") from exc
    except InterviewFinished as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    reply_text = result.get("reply", "")
    # M4: engine values pass through untouched — never fabricate latency/route.
    served_by = result.get("served_by")
    turn_num = result.get("turn_number")
    latency_ms = result.get("latency_ms")
    topic = result.get("topic", "general")
    topics_explored = result.get("topics_explored", {})
    suggested_questions = result.get("suggested_questions", [])
    is_finished = result.get("is_finished", False)
    # Deterministic consistency signals from the engine (quality layer, never
    # infra): numeric self-contradiction + identity drift. Surfaced so the UI
    # can flag the turn instead of the judge having to read metadata_json.
    consistency = {
        "contradiction_detected": bool(result.get("contradiction_detected", False)),
        "contradiction_details": result.get("contradiction_details"),
        "identity_drift": bool(result.get("identity_drift", False)),
        "drift_notes": result.get("drift_notes") or [],
    }

    return {
        "reply": reply_text,
        "turn_number": turn_num,
        "served_by": served_by,
        "latency_ms": latency_ms,
        "topic": topic,
        "topics_explored": topics_explored,
        "turn_count": result.get("turn_count", turn_num),
        "max_turns": result.get("max_turns"),
        "is_finished": is_finished,
        "suggested_questions": suggested_questions,
        **consistency,
        "user_message": {
            "role": "researcher",
            "content": text.strip(),
            "timestamp": now_iso,
            "turn_number": turn_num - 1,
            "topic": topic,
        },
        "persona_reply": {
            "role": "persona",
            "content": reply_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "served_by": served_by,
            "turn_number": turn_num,
            "topic": topic,
            "retrieved_memories": result.get("retrieved_memories", []),
            **consistency,
        },
    }


@router.post("/studies/{study_id}/interviews/{interview_id}/messages/stream")
@limiter.limit("30/minute")
async def post_study_interview_message_stream(
    study_id: str,
    interview_id: str,
    body: InterviewMessageRequest,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE variant of the message endpoint: `delta` events as the persona
    speaks, then one `done` event with the canonical ask() payload (normalized
    reply + provenance). Errors after headers are sent arrive as `error` events
    carrying the same ``error_code`` values as the JSON envelope."""
    await _get_study_and_verify_access(session, study_id, current_user, write=True)

    _require_interview_in_study(
        await session.get(Conversations, interview_id), study_id, current_user, write=True
    )

    text = body.content or body.message
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    engine = request.app.state.interview_engine
    http_request_id = request_id_of(request)

    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _error(kind: str, error_code: str, detail: str, **fields: Any) -> str:
        payload = {"kind": kind, "error_code": error_code, "detail": detail, "request_id": http_request_id}
        payload.update(fields)
        return _sse("error", payload)

    async def event_source():
        try:
            # aclosing: deterministic cleanup of the whole generator chain on
            # client disconnect, not GC-scheduled finalization.
            async with aclosing(engine.ask_stream(interview_id, text.strip())) as agen:
                async for item in agen:
                    if item.get("type") == "delta":
                        yield _sse("delta", {"text": item["text"]})
                    elif item.get("type") == "done":
                        payload = {k: v for k, v in item.items() if k != "type"}
                        now_iso = datetime.now(timezone.utc).isoformat()
                        # Contract parity with the non-stream endpoint (M4 fields).
                        payload["user_message"] = {
                            "role": "researcher",
                            "content": text.strip(),
                            "timestamp": now_iso,
                            "turn_number": (payload.get("turn_number") or 1) - 1,
                            "topic": payload.get("topic"),
                        }
                        payload["persona_reply"] = {
                            "role": "persona",
                            "content": payload.get("reply"),
                            "timestamp": now_iso,
                            "turn_number": payload.get("turn_number"),
                            "topic": payload.get("topic"),
                            "latency_ms": payload.get("latency_ms"),
                            "served_by": payload.get("served_by"),
                            "retrieved_memories": payload.get("retrieved_memories", []),
                        }
                        yield _sse("done", payload)
        except InterviewFinished as exc:
            yield _error("finished", "interview_finished", str(exc))
        except (ConversationNotFound, PersonaNotFound) as exc:
            yield _error("not_found", "not_found", str(exc))
        except ContextWindowExceeded as exc:
            yield _error(
                "context_window",
                "context_window_exceeded",
                f"This request needs ~{exc.estimated_tokens} tokens of context; no eligible "
                "model can hold it. Nothing was truncated.",
                estimated_tokens=exc.estimated_tokens,
                largest_window=exc.largest_window,
            )
        except AllCandidatesFailed as exc:
            yield _error(
                "no_route",
                "all_candidates_failed",
                "No AI route could serve this request — all candidates failed.",
                llm_request_id=exc.provenance.request_id,
                attempts=[
                    {
                        "provider": a.provider,
                        "model": a.model,
                        "failure_kind": str(a.failure_kind) if a.failure_kind else None,
                        "fallback_reason": a.fallback_reason,
                    }
                    for a in exc.provenance.attempts
                ],
                routing_path=list(exc.provenance.routing_path),
            )
        except Exception:
            logger.warning("interview stream failed for %s", interview_id, exc_info=True)
            yield _error("generic", "internal_error", "interview turn failed")

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/studies/{study_id}/interviews/{interview_id}/complete")
@limiter.limit("10/minute")
async def complete_study_interview(
    study_id: str,
    interview_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Finish the interview, extract structured insights with turn provenance, and generate executive summary."""
    await _get_study_and_verify_access(session, study_id, current_user, write=True)

    _require_interview_in_study(
        await session.get(Conversations, interview_id), study_id, current_user, write=True
    )

    try:
        synthesis = await request.app.state.interview_engine.complete(interview_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Interview not found") from exc

    return synthesis


@router.get("/studies/{study_id}/interviews/{interview_id}/insights")
async def get_study_interview_insights(
    study_id: str,
    interview_id: str,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List structured insights extracted from this interview."""
    await _get_study_and_verify_access(session, study_id, current_user)

    _require_interview_in_study(
        await session.get(Conversations, interview_id), study_id, current_user
    )

    stmt = select(InterviewInsights).where(InterviewInsights.interview_id == interview_id)
    insights = list((await session.execute(stmt)).scalars())
    return [_serialize_insight(i) for i in insights]


# ============================================================================
# Legacy Endpoints (Phase 10 & Integration Compatibility)
# ============================================================================

async def _guard_legacy_persona(
    request: Request, persona_id: str, current_user: Optional[Users]
) -> None:
    """Owner gate for un-nested legacy endpoints: anonymous callers may only
    touch shared/system personas, never another tenant's (B6 stage 3)."""
    async with request.app.state.db_sessionmaker() as session:
        p_row = await session.get(Personas, persona_id)
    # Missing row falls through — the engine raises PersonaNotFound canonically.
    if p_row is not None and not owner_accessible(p_row.owner_id, current_user):
        raise HTTPException(status_code=404, detail="persona not found")


async def _guard_legacy_conversation(
    request: Request, conversation_id: str, current_user: Optional[Users], *, write: bool = False
) -> None:
    """Owner gate for conversation-id-addressed legacy endpoints — checks the
    conversation's own tenant stamp, then its persona's owner.

    ``write=True`` uses the stricter write predicate: appending turns to a
    shared-pool conversation is a mutation, and the shared pool is a read pool
    only — otherwise any caller could hijack another visitor's transcript."""
    predicate = owner_can_write if write else owner_accessible
    async with request.app.state.db_sessionmaker() as session:
        conv = await session.get(Conversations, conversation_id)
        if conv is None:
            return  # engine raises ConversationNotFound canonically
        if not predicate(conv.user_id, current_user):
            raise HTTPException(status_code=404, detail="conversation not found")
        if conv.persona_id:
            p_row = await session.get(Personas, conv.persona_id)
            if p_row is not None and not owner_accessible(p_row.owner_id, current_user):
                raise HTTPException(status_code=404, detail="conversation not found")


@router.post("/personas/{persona_id}/conversations", status_code=201)
async def start_conversation_under_persona(
    persona_id: str,
    body: ConversationCreate,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> dict:
    await _guard_legacy_persona(request, persona_id, current_user)
    try:
        conversation = await request.app.state.interview_engine.start(
            persona_id, body.objective,
            user_id=current_user.id if current_user else None,
        )
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    return {
        "id": conversation.id,
        "persona_id": conversation.persona_id,
        "objective": conversation.objective,
        "status": conversation.status,
        "turns": [],
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
    }


@router.post("/conversations", status_code=201)
async def start_conversation(
    body: ConversationCreate,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> dict:
    if not body.persona_id:
        raise HTTPException(status_code=422, detail="persona_id is required")
    await _guard_legacy_persona(request, body.persona_id, current_user)
    try:
        conversation = await request.app.state.interview_engine.start(
            body.persona_id, body.objective,
            user_id=current_user.id if current_user else None,
        )
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    return {
        "id": conversation.id,
        "persona_id": conversation.persona_id,
        "objective": conversation.objective,
        "status": conversation.status,
        "turns": [],
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
    }


@router.post("/conversations/{conversation_id}/messages")
@limiter.limit("30/minute")
async def post_message(
    conversation_id: str,
    body: MessageIn,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    text = body.content or body.message
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="message content cannot be empty")
    await _guard_legacy_conversation(request, conversation_id, current_user, write=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        result = await request.app.state.interview_engine.ask(conversation_id, text.strip())
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    except InterviewFinished as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # LLM-layer failures (413/503) are rendered by the global handlers.

    reply_text = result.get("reply", "")
    # M4: engine values pass through untouched — never fabricate latency/route.
    served_by = result.get("served_by")
    turn_num = result.get("turn_number")

    return {
        "reply": reply_text,
        "turn_number": turn_num,
        "served_by": served_by,
        "conversation_id": conversation_id,
        "user_message": {
            "role": "user",
            "content": text.strip(),
            "timestamp": now_iso,
        },
        "persona_reply": {
            "role": "assistant",
            "content": reply_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": result.get("latency_ms"),
            "served_by": served_by,
            "retrieved_memories": result.get("retrieved_memories", []),
        },
    }


# ---------------------------------------------------------------------------
# Batch interview jobs (async): a batch of N personas × M questions runs for
# many minutes at real free-tier latency, far beyond any sane HTTP timeout.
# The POST starts a background job and returns immediately; the UI polls.
# Registry is in-memory (dev-scale): a restart loses job STATUS, never data —
# completed interviews are persisted as conversations as they finish.
# ---------------------------------------------------------------------------

def _batch_registry(app) -> dict[str, dict[str, Any]]:
    reg = getattr(app.state, "interview_batch_jobs", None)
    if reg is None:
        reg = {}
        app.state.interview_batch_jobs = reg
        app.state.interview_batch_tasks = set()
    return reg


_BATCH_TURN_RETRY_DELAY_S = 20.0  # one provider-wide cooldown window is 30-60 s


async def _ask_with_one_retry(engine, conversation_id: str, question: str, entry: dict[str, Any]) -> None:
    """One interview turn; a transient route exhaustion (every candidate cooling
    or timing out at once) is retried ONCE after a pause and recorded in the
    job entry. Anything else — and a second exhaustion — propagates: the turn
    is never faked and the interview is marked failed honestly."""
    try:
        await engine.ask(conversation_id, question)
    except AllCandidatesFailed:
        entry["retried_turns"] = int(entry.get("retried_turns") or 0) + 1
        logger.info("batch turn exhausted all routes for %s; retrying once in %.0fs", conversation_id, _BATCH_TURN_RETRY_DELAY_S)
        await asyncio.sleep(_BATCH_TURN_RETRY_DELAY_S)
        await engine.ask(conversation_id, question)


async def _run_batch_job(
    app,
    job: dict[str, Any],
    personas: list[dict[str, str]],
    questions: list[str],
    study_id: str,
    study_goal: str,
    study_prompt: Optional[str],
    user_id: str,
) -> None:
    engine = getattr(app.state, "interview_engine", None)
    for p in personas:
        entry = job["personas"][p["id"]]
        if engine is None:
            entry["status"] = "failed"
            entry["error"] = "interview engine unavailable (LLM router / DB not wired)"
            continue
        entry["status"] = "in_progress"
        try:
            conv = await engine.start(
                persona_id=p["id"],
                objective=study_goal,
                study_id=study_id,
                user_id=user_id,
                custom_objective=study_prompt,
                length_tier="standard",
            )
            for q in questions:
                await _ask_with_one_retry(engine, conv.id, q, entry)
            await engine.complete(conv.id)
            entry["status"] = "completed"
            entry["interview_id"] = conv.id
            job["completed_count"] += 1
        except Exception as exc:
            logger.warning(
                "batch-run job %s: interview failed for persona %s",
                job["job_id"], p["id"], exc_info=True,
            )
            entry["status"] = "failed"
            entry["error"] = f"{exc.__class__.__name__}: interview failed"
            job["failed_count"] += 1
    job["status"] = "completed" if job["failed_count"] == 0 else (
        "completed_with_failures" if job["completed_count"] > 0 else "failed"
    )
    job["finished_at"] = datetime.now(timezone.utc).isoformat()


@router.post("/studies/{study_id}/interviews/batch-run", status_code=202)
@limiter.limit("5/minute")
async def batch_run_study_interviews(
    study_id: str,
    payload: Optional[BatchInterviewRunRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Start a background batch-interview job across study personas; poll its status endpoint."""
    study = await _get_study_and_verify_access(session, study_id, current_user, write=True)
    effective_user_id = (current_user.id if current_user else None) or study.user_id or ANONYMOUS_OWNER_ID

    # 1. Resolve personas
    target_persona_ids = payload.persona_ids if payload and payload.persona_ids else []
    if not target_persona_ids:
        p_stmt = select(Personas).where(Personas.study_id == study_id)
        personas = list((await session.execute(p_stmt)).scalars().all())
    else:
        # Client-supplied ids are scoped to this study: an unscoped `IN` let a
        # caller interview another tenant's persona and read the transcript back.
        p_stmt = select(Personas).where(
            Personas.id.in_(target_persona_ids), Personas.study_id == study_id
        )
        personas = list((await session.execute(p_stmt)).scalars().all())
        if len(personas) != len(set(target_persona_ids)):
            raise HTTPException(
                status_code=400, detail="One or more personas do not belong to this study"
            )

    if not personas:
        raise HTTPException(status_code=400, detail="No personas available for this study")

    # 2. Resolve questions — the study's generated script or the caller's own
    # list. There is no default questionnaire: a script must exist first (R2).
    questions = [q for q in ((payload and payload.questions) or study.script_questions or []) if str(q).strip()]
    if not questions:
        raise APIError(
            400,
            "This study has no interview script yet. Generate the script (or pass your own questions) before running interviews.",
            error_code="script_required",
        )

    if getattr(request.app.state, "interview_engine", None) is None:
        llm_router = getattr(request.app.state, "llm_router", None)
        session_maker = getattr(request.app.state, "db_sessionmaker", None)
        memory = getattr(request.app.state, "memory_service", None)
        if session_maker and llm_router:
            request.app.state.interview_engine = InterviewEngine(
                llm_router, session_maker, memory=memory, suggest_questions=True
            )
    if getattr(request.app.state, "interview_engine", None) is None:
        raise LLMUnavailable("Batch interviews")

    # Detach plain values before the request session closes.
    personas_data = [{"id": p.id, "name": p.name} for p in personas]

    job_id = f"bjob_{uuid.uuid4().hex[:12]}"
    job: dict[str, Any] = {
        "job_id": job_id,
        "study_id": study_id,
        "status": "running",
        "total_personas": len(personas_data),
        "completed_count": 0,
        "failed_count": 0,
        "question_count": len(questions),
        "personas": {
            p["id"]: {"persona_id": p["id"], "persona_name": p["name"], "status": "pending"}
            for p in personas_data
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    registry = _batch_registry(request.app)
    registry[job_id] = job
    # Keep only the most recent jobs.
    while len(registry) > 50:
        registry.pop(next(iter(registry)))

    task = asyncio.create_task(
        _run_batch_job(
            request.app, job, personas_data, list(questions),
            study_id, study.goal or "demand_validation", study.prompt, effective_user_id,
        )
    )
    request.app.state.interview_batch_tasks.add(task)
    task.add_done_callback(request.app.state.interview_batch_tasks.discard)

    return {
        "job_id": job_id,
        "study_id": study_id,
        "status": "running",
        "total_personas": job["total_personas"],
        "personas": job["personas"],
    }


@router.get("/studies/{study_id}/interviews/batch-run/{job_id}")
async def get_batch_run_status(
    study_id: str,
    job_id: str,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Poll a batch interview job. 404 for unknown/lost jobs (e.g. after a restart)."""
    await _get_study_and_verify_access(session, study_id, current_user)
    job = _batch_registry(request.app).get(job_id)
    if not job or job["study_id"] != study_id:
        raise HTTPException(status_code=404, detail="batch job not found (it may have been lost in a server restart)")
    return job


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
) -> dict:
    await _guard_legacy_conversation(request, conversation_id, current_user)
    try:
        conversation, turns = await request.app.state.interview_engine.transcript(conversation_id)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    return {
        "id": conversation.id,
        "persona_id": conversation.persona_id,
        "objective": conversation.objective,
        "status": conversation.status,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "turns": [
            {
                "id": t.id,
                "turn_number": t.turn_number,
                "role": t.role,
                "content": t.content,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in turns
        ],
    }

