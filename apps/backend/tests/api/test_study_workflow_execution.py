"""Private study execution uses closed read transactions and guarded finalization."""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.api.copilot import router as copilot_router
from bebshax.api.errors import register_exception_handlers
from bebshax.api.limiter import limiter
from bebshax.api.studies import router as studies_router
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Studies
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.governance import get_llm_request_context


@pytest.fixture
async def workflow_api(tmp_path) -> AsyncIterator[tuple]:
    database = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    opened_sessions = []

    class TrackedSession(AsyncSession):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            opened_sessions.append(self)

    maker = async_sessionmaker(database, class_=TrackedSession, expire_on_commit=False)
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as session:
        session.add(Users(
            id="workflow-owner", email="workflow@example.test", full_name="Workflow Owner",
            is_verified=True, is_active=True, auth_provider="email",
        ))
        session.add(Studies(
            id="workflow-study", user_id="workflow-owner", title="Synthetic meal study",
            prompt="Complete meal context " * 150 + "full-context-tail",
            script_questions=["Original saved question"],
        ))
        await session.commit()
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="workflow", context_window=100000),
        reply=json.dumps({
            "reply": "Which meal choices are difficult today?",
            "questions": ["How do you plan meals?", "What makes meal planning difficult?"],
            "roles": [{"role": "MEAL PLANNER", "description": "A synthetic meal-planning role"}],
        }),
    )])
    app = FastAPI()
    app.state.db_sessionmaker = maker
    app.state.limiter = limiter
    app.state.llm_service = SingleAdapterLLMService(adapter)
    app.state.llm_router = app.state.llm_service
    register_exception_handlers(app)
    app.include_router(studies_router, prefix="/api")
    app.include_router(copilot_router, prefix="/api")
    headers = {"Authorization": f"Bearer {create_access_token('workflow-owner')}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
            yield client, maker, adapter, opened_sessions
    finally:
        await app.state.llm_service.aclose()
        await database.dispose()


async def test_script_closes_context_transaction_before_inference(workflow_api, monkeypatch):
    client, maker, adapter, opened_sessions = workflow_api
    original = adapter.complete

    async def observe(candidate, request):
        assert not any(session.in_transaction() for session in opened_sessions)
        assert "full-context-tail" in request.messages[-1].content
        assert request.owner_user_id == "workflow-owner"
        assert request.study_id == "workflow-study"
        context = get_llm_request_context()
        assert (context.owner_user_id, context.study_id, context.data_classification) == (
            "workflow-owner", "workflow-study", "private",
        )
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    response = await client.post("/api/studies/workflow-study/script/generate")
    assert response.status_code == 200
    async with maker() as session:
        study = await session.get(Studies, "workflow-study")
        assert study.script_questions == response.json()["questions"]
        assert study.script_meta["llm_request_id"] == response.json()["llm_request_id"]


async def test_script_rejects_context_changed_during_inference(workflow_api, monkeypatch):
    client, maker, adapter, opened_sessions = workflow_api
    original = adapter.complete

    async def change_study(candidate, request):
        async with maker() as session:
            study = await session.get(Studies, "workflow-study")
            study.prompt = "Changed research context"
            study.script_questions = ["Newer saved question"]
            await session.commit()
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", change_study)
    response = await client.post("/api/studies/workflow-study/script/generate")
    assert response.status_code == 409
    async with maker() as session:
        study = await session.get(Studies, "workflow-study")
        assert study.script_questions == ["Newer saved question"]
        assert study.revision == 2


@pytest.mark.parametrize("path,body,study_id", [
    ("/api/study/copilot", {"study_id": "workflow-study", "messages": [
        {"role": "user", "content": "Synthetic meal planning question"},
    ]}, "workflow-study"),
    ("/api/study/suggest-roles", {"study_prompt": "Synthetic meal planning"}, None),
])
async def test_copilot_requests_have_private_verified_context(workflow_api, monkeypatch, path, body, study_id):
    client, maker, adapter, opened_sessions = workflow_api
    original = adapter.complete

    async def observe(candidate, request):
        context = get_llm_request_context()
        assert context is not None
        assert (context.owner_user_id, context.study_id, context.data_classification) == (
            "workflow-owner", study_id, "private",
        )
        assert request.owner_user_id == "workflow-owner"
        assert request.study_id == study_id
        assert not any(session.in_transaction() for session in opened_sessions)
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    response = await client.post(path, json=body)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/api/studies/missing/script/generate", "/api/studies/missing/research/run"])
async def test_missing_study_is_guarded_before_execution(workflow_api, path):
    client, maker, adapter, opened_sessions = workflow_api
    response = await client.post(path)
    assert response.status_code == 404
    assert adapter.requests == []