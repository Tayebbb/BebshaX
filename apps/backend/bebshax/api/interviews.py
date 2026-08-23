"""Interview REST API (Phase 10)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bebshax.interview.engine import ConversationNotFound, PersonaNotFound
from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded

router = APIRouter(tags=["interviews"])


class ConversationCreate(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)


class MessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


@router.post("/personas/{persona_id}/conversations", status_code=201)
async def start_conversation(persona_id: str, body: ConversationCreate, request: Request) -> dict:
    try:
        conversation = await request.app.state.interview_engine.start(persona_id, body.objective)
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    return {
        "id": conversation.id,
        "persona_id": conversation.persona_id,
        "objective": conversation.objective,
        "status": conversation.status,
    }


@router.post("/conversations/{conversation_id}/messages")
async def post_message(conversation_id: str, body: MessageIn, request: Request) -> dict:
    try:
        return await request.app.state.interview_engine.ask(conversation_id, body.message)
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    except PersonaNotFound as exc:
        raise HTTPException(status_code=404, detail="persona not found") from exc
    except ContextWindowExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllCandidatesFailed as exc:
        raise HTTPException(
            status_code=503, detail="no LLM route could serve this request"
        ) from exc


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
        "turns": [
            {"turn_number": t.turn_number, "role": t.role, "content": t.content} for t in turns
        ],
    }
