"""Persona REST API: businesses, generation, retrieval (Phase 8)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from bebshax.llm import AllCandidatesFailed, ContextWindowExceeded
from bebshax.persona.generation import PersonaGenerationFailed
from bebshax.persona.store import (
    create_business,
    get_business,
    list_businesses,
    load_persona,
    save_persona,
)

router = APIRouter(tags=["personas"])


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=8000)


class PersonaGenerateRequest(BaseModel):
    hints: str | None = Field(default=None, max_length=2000)


@router.post("/businesses", status_code=201)
async def create_business_endpoint(body: BusinessCreate, request: Request) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        business = await create_business(session, body.name, body.description)
    return {"id": business.id, "name": business.name, "description": business.description}


@router.get("/businesses")
async def list_businesses_endpoint(request: Request) -> list[dict]:
    async with request.app.state.db_sessionmaker() as session:
        businesses = await list_businesses(session)
    return [{"id": b.id, "name": b.name, "description": b.description} for b in businesses]


@router.post("/businesses/{business_id}/personas", status_code=201)
async def generate_persona_endpoint(
    business_id: str, body: PersonaGenerateRequest, request: Request
) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        business = await get_business(session, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="business not found")

    engine = request.app.state.persona_engine
    try:
        profile = await engine.generate(
            business_id=business.id,
            business_name=business.name,
            business_description=business.description or "",
            hints=body.hints,
        )
    except PersonaGenerationFailed as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason": exc.reason, "violations": [v.message for v in exc.violations]},
        ) from exc
    except ContextWindowExceeded as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except AllCandidatesFailed as exc:
        raise HTTPException(
            status_code=503, detail="no LLM route could serve this request"
        ) from exc

    async with request.app.state.db_sessionmaker() as session:
        await save_persona(session, profile)
    return profile.model_dump(mode="json")


@router.get("/personas/{persona_id}")
async def get_persona_endpoint(persona_id: str, request: Request) -> dict:
    async with request.app.state.db_sessionmaker() as session:
        profile = await load_persona(session, persona_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return profile.model_dump(mode="json")
