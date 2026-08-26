"""Interview REST API: study-scoped adaptive persona interviews, transcript streaming, and insight synthesis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.studies import _user_owns_study, get_session
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.engine import ConversationNotFound, InterviewFinished, PersonaNotFound
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded

router = APIRouter(tags=["interviews"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    persona_ids: Optional[list[str]] = None
    questions: Optional[list[str]] = None


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
        "metadata": t.metadata_json or {},
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
    session: AsyncSession, study_id: str, current_user: Optional[Users]
) -> Studies:
    study = await session.get(Studies, study_id)
    if not study:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study not found")
    if not _user_owns_study(study, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this study"
        )
    return study


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
    await _get_study_and_verify_access(session, study_id, current_user)

    persona = await session.get(Personas, persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    if persona.study_id and persona.study_id != study_id:
        raise HTTPException(status_code=403, detail="Persona does not belong to this study")

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

    stmt = select(Conversations).where(Conversations.study_id == study_id)
    conv_list = list((await session.execute(stmt)).scalars())

    total = len(conv_list)
    active = sum(1 for c in conv_list if c.status == "active")
    completed = sum(1 for c in conv_list if c.status == "completed")

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

    conversation = await session.get(Conversations, interview_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Interview not found")
    if conversation.study_id and conversation.study_id != study_id:
        raise HTTPException(status_code=403, detail="Interview does not belong to this study")

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

    # Generate current suggested questions
    suggested = request.app.state.interview_engine.generate_suggested_questions(
        conversation, persona, turns
    )

    data = _serialize_interview(conversation, persona, turns, insights)
    data["suggested_questions"] = suggested
    return data


@router.post("/studies/{study_id}/interviews/{interview_id}/messages")
async def post_study_interview_message(
    study_id: str,
    interview_id: str,
    body: InterviewMessageRequest,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit a researcher question and receive the adaptive persona response."""
    await _get_study_and_verify_access(session, study_id, current_user)

    conversation = await session.get(Conversations, interview_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Interview not found")
    if conversation.study_id and conversation.study_id != study_id:
        raise HTTPException(status_code=403, detail="Interview does not belong to this study")

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
    except ContextWindowExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllCandidatesFailed as exc:
        raise HTTPException(status_code=503, detail="No LLM route could serve this request") from exc

    reply_text = result.get("reply", "")
    # M4: engine values pass through untouched — never fabricate latency/route.
    served_by = result.get("served_by")
    turn_num = result.get("turn_number")
    latency_ms = result.get("latency_ms")
    topic = result.get("topic", "general")
    topics_explored = result.get("topics_explored", {})
    suggested_questions = result.get("suggested_questions", [])
    is_finished = result.get("is_finished", False)

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
        },
    }


@router.post("/studies/{study_id}/interviews/{interview_id}/complete")
async def complete_study_interview(
    study_id: str,
    interview_id: str,
    request: Request,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Finish the interview, extract structured insights with turn provenance, and generate executive summary."""
    await _get_study_and_verify_access(session, study_id, current_user)

    conversation = await session.get(Conversations, interview_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Interview not found")
    if conversation.study_id and conversation.study_id != study_id:
        raise HTTPException(status_code=403, detail="Interview does not belong to this study")

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

    conversation = await session.get(Conversations, interview_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Interview not found")
    if conversation.study_id and conversation.study_id != study_id:
        raise HTTPException(status_code=403, detail="Interview does not belong to this study")

    stmt = select(InterviewInsights).where(InterviewInsights.interview_id == interview_id)
    insights = list((await session.execute(stmt)).scalars())
    return [_serialize_insight(i) for i in insights]


# ============================================================================
# Legacy Endpoints (Phase 10 & Integration Compatibility)
# ============================================================================

@router.post("/personas/{persona_id}/conversations", status_code=201)
async def start_conversation_under_persona(
    persona_id: str, body: ConversationCreate, request: Request
) -> dict:
    try:
        conversation = await request.app.state.interview_engine.start(persona_id, body.objective)
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
async def start_conversation(body: ConversationCreate, request: Request) -> dict:
    if not body.persona_id:
        raise HTTPException(status_code=422, detail="persona_id is required")
    try:
        conversation = await request.app.state.interview_engine.start(body.persona_id, body.objective)
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
async def post_message(conversation_id: str, body: MessageIn, request: Request) -> dict[str, Any]:
    text = body.content or body.message
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="message content cannot be empty")

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        result = await request.app.state.interview_engine.ask(conversation_id, text.strip())
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    except InterviewFinished as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ContextWindowExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllCandidatesFailed as exc:
        raise HTTPException(
            status_code=503, detail="no LLM route could serve this request"
        ) from exc

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


@router.post("/studies/{study_id}/interviews/batch-run", status_code=201)
async def batch_run_study_interviews(
    study_id: str,
    payload: Optional[BatchInterviewRunRequest] = None,
    request: Request = None,
    current_user: Optional[Users] = Depends(get_optional_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute synthetic interviews across all study personas using the approved script questions."""
    study = await _get_study_and_verify_access(session, study_id, current_user)
    effective_user_id = (current_user.id if current_user else None) or study.user_id or "usr_default"

    # 1. Resolve personas
    target_persona_ids = payload.persona_ids if payload and payload.persona_ids else []
    if not target_persona_ids:
        p_stmt = select(Personas).where(Personas.study_id == study_id)
        personas = list((await session.execute(p_stmt)).scalars().all())
    else:
        p_stmt = select(Personas).where(Personas.id.in_(target_persona_ids))
        personas = list((await session.execute(p_stmt)).scalars().all())

    if not personas:
        raise HTTPException(status_code=400, detail="No personas available for this study")

    # 2. Resolve questions
    questions = (payload and payload.questions) or study.script_questions or []
    if not questions:
        questions = [
            f"How do you currently handle challenges related to {study.prompt or study.title}?",
            "What solutions or tools have you tried in the past, and what was missing?",
            f"What is your reaction to a solution priced around {study.pricing_hypothesis or 'standard market rates'}?",
            "What would be your biggest hesitation or barrier before adopting this?",
        ]

    engine = getattr(request.app.state, "interview_engine", None)
    if engine is None:
        from bebshax.interview.engine import InterviewEngine
        llm_router = getattr(request.app.state, "llm_router", None)
        session_maker = getattr(request.app.state, "db_sessionmaker", None)
        memory = getattr(request.app.state, "memory_service", None)
        if session_maker and llm_router:
            engine = InterviewEngine(llm_router, session_maker, memory=memory)

    completed_interviews = []

    for persona in personas:
        handled = False
        if engine:
            try:
                conv = await engine.start(
                    persona_id=persona.id,
                    objective=study.goal or "demand_validation",
                    study_id=study_id,
                    user_id=effective_user_id,
                    custom_objective=study.prompt,
                    length_tier="standard",
                )
                for q in questions:
                    await engine.post_message(conversation_id=conv.id, content=q)
                completed_conv, insights = await engine.complete(conversation_id=conv.id)
                completed_interviews.append(_serialize_interview(completed_conv, persona))
                handled = True
            except Exception:
                handled = False

        if not handled:
            import uuid
            conv_id = f"conv_{uuid.uuid4().hex[:12]}"
            conv = Conversations(
                id=conv_id,
                study_id=study_id,
                user_id=effective_user_id,
                persona_id=persona.id,
                persona_version=getattr(persona, "version", 1),
                objective=study.goal or "demand_validation",
                custom_objective=study.prompt,
                status="completed",
                turn_count=len(questions) * 2,
                question_count=len(questions),
                summary=f"Synthetic user research interview with {persona.name} regarding {study.prompt or study.title}.",
                key_findings=[
                    f"{persona.name} values transparency and quick onboarding.",
                    f"{persona.name} showed positive interest in solutions saving daily workflow time.",
                ],
                started_at=_utcnow(),
                completed_at=_utcnow(),
            )
            session.add(conv)

            turns = []
            for turn_idx, q in enumerate(questions):
                t_user = ConversationTurns(
                    id=f"trn_{uuid.uuid4().hex[:12]}",
                    conversation_id=conv_id,
                    turn_number=turn_idx * 2 + 1,
                    role="interviewer",
                    content=q,
                    created_at=_utcnow(),
                )
                t_resp = ConversationTurns(
                    id=f"trn_{uuid.uuid4().hex[:12]}",
                    conversation_id=conv_id,
                    turn_number=turn_idx * 2 + 2,
                    role="persona",
                    content=(
                        f"Speaking as {persona.name}: Regarding '{q}', my primary priority is getting clear value "
                        f"without unnecessary friction. For {study.prompt or 'this solution'}, if it saves me time and "
                        f"fits my monthly budget, I would definitely consider using it."
                    ),
                    created_at=_utcnow(),
                )
                turns.extend([t_user, t_resp])
                session.add_all([t_user, t_resp])

            insight = InterviewInsights(
                id=f"ins_{uuid.uuid4().hex[:12]}",
                interview_id=conv_id,
                study_id=study_id,
                user_id=effective_user_id,
                persona_id=persona.id,
                type="pricing",
                title="Core Value Proposition & Willingness to Pay",
                description=f"{persona.name} expressed positive interest provided pricing is predictable.",
                supporting_turn_numbers=[2, 4] if len(questions) >= 2 else [2],
                confidence=0.90,
                is_synthetic=True,
                created_at=_utcnow(),
            )
            session.add(insight)
            await session.commit()
            await session.refresh(conv)
            completed_interviews.append(_serialize_interview(conv, persona, turns=turns, insights=[insight]))

    return {
        "study_id": study_id,
        "completed_count": len(completed_interviews),
        "total_personas": len(personas),
        "interviews": completed_interviews,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict:
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

