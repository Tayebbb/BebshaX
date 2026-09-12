import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.api.errors import register_exception_handlers
from bebshax.api.interviews import router
from bebshax.api.personas import router as persona_router
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Personas, Studies
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations
from bebshax.llm import LLMResult, LLMService, TaskType
from bebshax.llm.adapters.base import StreamDelta
from bebshax.llm.adapters.embeddings import HashEmbedding
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord
from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryService


class TenantLLM(LLMService):
    def __init__(self):
        self.requests = []
        self.text = "I compare meal prices."
        self.stream_failure = None
        self.deadlines = []

    async def complete(self, request, *, deadline_at=None):
        self.requests.append(request)
        self.deadlines.append(deadline_at)
        return LLMResult(
            text=self.text, provider="fake", model="tenant-test",
            provenance=ProvenanceRecord(
                request_id=request.request_id, task=request.task, success=True,
                persona_id=request.persona_id, conversation_id=request.conversation_id,
                served_by_provider="fake", served_by_model="tenant-test",
            ),
        )

    async def stream(self, request, *, deadline_at=None):
        if self.stream_failure:
            yield StreamDelta(text="Provisional response")
            raise self.stream_failure
        yield await self.complete(request, deadline_at=deadline_at)


@pytest_asyncio.fixture
async def tenant_api(tmp_path):
    database = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tenants.db'}")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = sessionmaker(database, class_=AsyncSession, expire_on_commit=False)
    llm = TenantLLM()
    memory = MemoryService(maker, HashEmbedding())
    engine = InterviewEngine(llm, maker, memory=memory)
    app = FastAPI()
    register_exception_handlers(app)
    app.state.db_sessionmaker = maker
    app.state.interview_engine = engine
    app.state.memory_service = memory
    app.include_router(router, prefix="/api")
    app.include_router(persona_router, prefix="/api")
    async with maker() as session:
        session.add_all([
            Users(id=owner, email=f"{owner}@example.invalid", full_name=owner,
                  is_active=True, is_verified=True, auth_provider="email")
            for owner in ("owner-first", "owner-second", "usr_system_holder")
        ])
        await session.flush()
        session.add(Personas(
            id="shared-persona", name="Synthetic shared persona", owner_id="usr_system_holder",
            demographics={"age": 28}, version=1,
        ))
        session.add(Studies(id="first-study", user_id="owner-first", title="Private study"))
        await session.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, maker, llm, engine
    finally:
        await database.dispose()


def headers(owner):
    return {"Authorization": f"Bearer {create_access_token(owner)}"}


@pytest.mark.parametrize("include_interviewer", [False, True])
async def test_persona_memory_listing_is_private_without_conversation_links(tenant_api, include_interviewer):
    client, maker, llm, engine = tenant_api
    memory = MemoryService(maker, HashEmbedding())
    for owner in ("owner-first", "owner-second"):
        await memory.remember("shared-persona", f"{owner} private reply", owner_id=owner)
        await memory.remember(
            "shared-persona", f"{owner} private question", owner_id=owner, source="interviewer",
        )
    async with maker() as session:
        session.add(MemoryItems(
            id="ambiguous-memory", persona_id="shared-persona", owner_id=None,
            text="Unknown legacy private content", kind="semantic", embedding=[0.0] * 384,
            embedding_space=HashEmbedding().space,
        ))
        await session.commit()

    response = await client.get(
        "/api/personas/shared-persona/memories",
        params={"include_interviewer": str(include_interviewer).lower()}, headers=headers("owner-first"),
    )

    assert response.status_code == 200
    expected = {"owner-first private reply"}
    if include_interviewer:
        expected.add("owner-first private question")
    assert {item["text"] for item in response.json()} == expected
    assert llm.requests == []


@pytest.mark.parametrize("authorization", [{}, {"Authorization": "Bearer invalid-token"}])
async def test_persona_memory_listing_requires_authentication(tenant_api, authorization):
    client, maker, llm, engine = tenant_api
    response = await client.get("/api/personas/shared-persona/memories", headers=authorization)
    assert response.status_code == 401
    assert llm.requests == []


async def test_two_authenticated_users_share_persona_but_not_memory_or_history(tenant_api):
    client, maker, llm, engine = tenant_api
    first = (await client.post("/api/conversations", headers=headers("owner-first"),
        json={"persona_id": "shared-persona", "objective": "Private first research"})).json()
    second = (await client.post("/api/conversations", headers=headers("owner-second"),
        json={"persona_id": "shared-persona", "objective": "Private second research"})).json()
    assert "id" in first and "id" in second
    response = await client.post(f"/api/conversations/{first['id']}/messages",
        headers=headers("owner-first"), json={"message": "How do you compare meal prices?"})
    assert response.status_code == 200
    llm.text = "Second synthetic owner's private meal preference."
    response = await client.post(f"/api/conversations/{second['id']}/messages",
        headers=headers("owner-second"), json={"message": "How do you compare meal prices?"})
    assert response.status_code == 200
    assert response.json()["persona_reply"]["retrieved_memories"] == []
    assert "I compare meal prices." not in llm.requests[-1].messages[0].content
    assert (await client.get(f"/api/conversations/{first['id']}", headers=headers("owner-second"))).status_code == 404
    assert (await client.get(f"/api/conversations/{first['id']}")).status_code == 404
    before = len(llm.requests)
    assert (await client.get(f"/api/conversations/{first['id']}", headers=headers("owner-first"))).status_code == 200
    assert len(llm.requests) == before
    assert all(deadline is not None for deadline in llm.deadlines)


async def test_unknown_owner_transcript_is_not_public(tenant_api):
    client, maker, llm, engine = tenant_api
    async with maker() as session:
        session.add(Conversations(id="unknown-transcript", persona_id="shared-persona", objective="Legacy unknown"))
        await session.commit()
    response = await client.get("/api/conversations/unknown-transcript", headers=headers("owner-second"))
    assert response.status_code == 404
    assert llm.requests == []


@pytest.mark.parametrize("kind", [FailureKind.TIMEOUT, FailureKind.SERVER_ERROR, FailureKind.MALFORMED_RESPONSE])
async def test_sse_preserves_post_output_failure_kind_and_provenance(tenant_api, kind):
    client, maker, llm, engine = tenant_api
    conversation = await engine.start("shared-persona", "Stream failures", study_id="first-study", user_id="owner-first")
    provenance = ProvenanceRecord(
        request_id="synthetic-stream-request", task=TaskType.PERSONA_INTERVIEW,
        persona_id="shared-persona", conversation_id=conversation.id,
        routing_path=["fake/tenant-test"], attempts=[AttemptRecord(
            attempt_number=1, provider="fake", model="tenant-test", failure_kind=kind,
        )],
    )
    llm.stream_failure = AttemptFailed(kind, "fake", "tenant-test", "private provider detail", provenance=provenance)
    response = await client.post(
        f"/api/studies/first-study/interviews/{conversation.id}/messages/stream",
        headers=headers("owner-first"), json={"content": "How do you choose meals?"},
    )
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert "event: done" not in response.text
    assert events[-1]["kind"] == kind.value
    assert events[-1]["llm_request_id"] == provenance.request_id
    assert events[-1]["attempts"][0]["failure_kind"] == kind.value
    assert events[-1]["routing_path"] == provenance.routing_path
    assert "private provider detail" not in response.text
    assert (await engine.transcript(conversation.id))[1] == []


async def test_api_deadline_includes_access_checks(tenant_api, monkeypatch):
    client, maker, llm, engine = tenant_api
    conversation = await engine.start("shared-persona", "Deadline at ingress", user_id="owner-first")
    from bebshax.api import interviews

    original = interviews._guard_legacy_conversation

    async def slow_guard(*args, **kwargs):
        await asyncio.sleep(0.15)
        return await original(*args, **kwargs)

    monkeypatch.setattr(interviews, "_guard_legacy_conversation", slow_guard)
    monkeypatch.setattr("bebshax.llm.latency.request_deadline_s", lambda task: 0.04)
    response = await client.post(f"/api/conversations/{conversation.id}/messages",
        headers=headers("owner-first"), json={"message": "How do you plan meals?"})
    assert response.status_code == 504
    assert llm.requests == []
    assert (await engine.transcript(conversation.id))[1] == []


@pytest.mark.parametrize("state", ["queued", "running", "interrupted"])
async def test_batch_poll_handles_unfinalized_durable_result(tenant_api, monkeypatch, state):
    client, maker, llm, engine = tenant_api

    async def stored_job(*args, **kwargs):
        return {
            "job_id": "batch-test", "user_id": "owner-first", "scope_id": "first-study",
            "status": "failed" if state == "interrupted" else "running", "state": state,
            "result": None, "result_refs": {"batch": {"total_personas": 2, "personas": {},
                "completed_count": 0, "failed_count": 0, "study_id": "first-study"}},
            "error": "Interrupted" if state == "interrupted" else None,
            "error_code": "job_interrupted" if state == "interrupted" else None,
            "finished_at": None,
        }

    monkeypatch.setattr("bebshax.api.interviews.get_job_async", stored_job)
    response = await client.get("/api/studies/first-study/interviews/batch-run/batch-test", headers=headers("owner-first"))
    assert response.status_code == 200
    assert response.json()["job_id"] == "batch-test"
    assert response.json()["total_personas"] == 2
    assert response.json()["status"] == ("failed" if state == "interrupted" else "running")
    assert llm.requests == []


async def test_cancelled_batch_retains_conversation_identity_and_durable_outcome(tenant_api, monkeypatch):
    from bebshax.api.interviews import _run_batch_job

    client, maker, llm, engine = tenant_api
    entered = asyncio.Event()

    async def wait_for_cancellation(request, *, deadline_at=None):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(llm, "complete", wait_for_cancellation)
    job = {
        "job_id": "cancelled-batch", "status": "running", "completed_count": 0, "failed_count": 0,
        "personas": {"shared-persona": {"status": "pending"}},
    }
    app = SimpleNamespace(state=SimpleNamespace(interview_engine=engine, db_sessionmaker=maker))
    task = asyncio.create_task(_run_batch_job(
        app, job, [{"id": "shared-persona", "name": "Shared source"}], ["How do you compare meals?"],
        "first-study", "Meal research", "Full synthetic context", "owner-first",
    ))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    entry = job["personas"]["shared-persona"]
    assert entry.get("interview_id")
    assert entry["status"] == "cancelled"
    saved, turns = await engine.transcript(entry["interview_id"], owner_id="owner-first")
    assert saved.status == "cancelled"
    assert saved.configuration["batch_execution"]["job_id"] == "cancelled-batch"
    assert turns == []
    assert engine._turn_locks == {}


async def test_batch_executes_private_turns_and_synthesis_through_fake_adapter(tenant_api, monkeypatch):
    from bebshax.api.interviews import _run_batch_job
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.governance import get_llm_request_context

    client, maker, llm, engine = tenant_api
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="batch"), replies=[
        "I compare meal prices.", '{"summary":"Meal prices matter.","insights":[]}',
    ])])
    contexts = []
    original = adapter.complete

    async def observe(candidate, request):
        contexts.append(get_llm_request_context())
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    engine = InterviewEngine(SingleAdapterLLMService(adapter), maker, memory=MemoryService(maker, HashEmbedding()))
    job = {
        "job_id": "private-batch", "status": "running", "completed_count": 0, "failed_count": 0,
        "personas": {"shared-persona": {"status": "pending"}},
    }
    app = SimpleNamespace(state=SimpleNamespace(interview_engine=engine, db_sessionmaker=maker))
    await _run_batch_job(
        app, job, [{"id": "shared-persona", "name": "Shared source"}], ["How do you compare meals?"],
        "first-study", "Meal research", "Full synthetic context", "owner-first",
    )
    assert job["status"] == "completed"
    assert len(contexts) == 2
    assert all(context.owner_user_id == "owner-first" and context.study_id == "first-study" for context in contexts)
    saved, turns = await engine.transcript(job["personas"]["shared-persona"]["interview_id"], owner_id="owner-first")
    assert saved.status == "completed" and len(turns) == 2