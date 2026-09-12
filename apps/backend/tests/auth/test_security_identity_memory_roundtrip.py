"""Offline session-to-memory round trips on the current FK-enforced SQL models."""

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError

from bebshax.api import interviews, personas, routes
from bebshax.api.errors import register_exception_handlers
from bebshax.auth.models import Users
from bebshax.db.models import Personas
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.embeddings import HashEmbedding
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.governance import get_llm_request_context
from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryService


@pytest.fixture
async def memory_identity_state(identity_state, monkeypatch):
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="security-memory"),
        reply="I compare meal prices.",
        replies=[
            "I compare meal prices.", "I compare meal prices.",
            '{"insights":["I compare the complete private first-owner meal observations."]}',
        ],
    )])
    contexts = []
    original = adapter.complete

    async def observe(candidate, request):
        contexts.append(get_llm_request_context())
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    service = SingleAdapterLLMService(adapter)
    memory = MemoryService(identity_state.sessions, HashEmbedding(), llm=service)
    interview = InterviewEngine(service, identity_state.sessions, memory=memory)
    identity_state.app.state.memory_service = memory
    identity_state.app.state.interview_engine = interview
    identity_state.app.include_router(interviews.router, prefix="/api")
    identity_state.app.include_router(personas.router, prefix="/api")
    register_exception_handlers(identity_state.app)
    async with identity_state.sessions() as session:
        assert await session.scalar(text("PRAGMA foreign_keys")) == 1
        session.add(Users(
            id="usr_system_holder", email="synthetic-source@example.test",
            full_name="Synthetic Source", is_active=True, is_verified=True,
        ))
        await session.flush()
        session.add(Personas(
            id="security-shared-persona", owner_id="usr_system_holder",
            name="Synthetic shared participant", demographics={"age": 28}, version=1,
        ))
        await session.commit()
    yield SimpleNamespace(
        identity=identity_state, memory=memory, interview=interview,
        adapter=adapter, contexts=contexts,
    )
    await interview.aclose()


async def _signin(client, email="owner@example.test", password="Identity123!") -> dict:
    response = await client.post("/api/auth/signin", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()


def _headers(credentials: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {credentials['access_token']}"}


async def test_shared_persona_roundtrip_preserves_private_memory_and_retrieval_audit(memory_identity_state):
    state = memory_identity_state
    client = state.identity.client
    conversations = {}
    credentials = {}
    remembered = {}
    for owner, email in (("usr_identity", "owner@example.test"), ("usr_other", "other@example.test")):
        credentials[owner] = await _signin(client, email)
        created = await client.post("/api/conversations", headers=_headers(credentials[owner]), json={
            "persona_id": "security-shared-persona", "objective": f"Private synthetic meal research for {owner}",
        })
        assert created.status_code == 201
        conversations[owner] = created.json()["id"]
        reply = await client.post(
            f"/api/conversations/{conversations[owner]}/messages", headers=_headers(credentials[owner]),
            json={"message": "How do you compare meal prices?"},
        )
        assert reply.status_code == 200
        assert reply.json()["persona_reply"]["retrieved_memories"] == []
        remembered[owner] = await state.memory.remember(
            "security-shared-persona", "I compare meal prices.", conversation_id=conversations[owner],
        )
        for index in range(8):
            await state.memory.remember(
                "security-shared-persona", f"I compare {owner} private meal observation {index}.",
                conversation_id=conversations[owner],
            )

    assert remembered["usr_identity"].id != remembered["usr_other"].id
    assert (await state.memory.remember(
        "security-shared-persona", "I compare meal prices.", conversation_id=conversations["usr_identity"],
    )).id == remembered["usr_identity"].id
    async with state.identity.sessions() as session:
        session.add(MemoryItems(
            id="security-unknown-memory", persona_id="security-shared-persona", owner_id=None,
            text="Unknown-owner private meal observation.", kind="episodic", source="persona",
            embedding=[0.0] * 384, embedding_space=HashEmbedding().space,
        ))
        await session.commit()

    reflected = await state.memory.reflect(
        "security-shared-persona", conversation_id=conversations["usr_identity"],
    )
    assert reflected and all(record.owner_id == "usr_identity" for record in reflected)
    reflection_prompt = state.adapter.requests[-1].messages[-1].content
    assert "usr_identity private meal observation 0" in reflection_prompt
    assert "usr_other private meal observation" not in reflection_prompt
    assert "Unknown-owner" not in reflection_prompt
    retrieved = await state.memory.retrieve(
        "security-shared-persona", "meal", conversation_id=conversations["usr_identity"],
        k=50, min_relevance=0, sources=None,
    )
    assert retrieved and all(record.owner_id == "usr_identity" for record in retrieved)
    listed = await client.get(
        "/api/personas/security-shared-persona/memories?include_interviewer=true",
        headers=_headers(credentials["usr_identity"]),
    )
    assert listed.status_code == 200
    assert {record["id"] for record in listed.json()} == {record.id for record in retrieved}
    assert (await client.get(
        f"/api/conversations/{conversations['usr_identity']}", headers=_headers(credentials["usr_other"]),
    )).status_code == 404

    reply = await client.post(
        f"/api/conversations/{conversations['usr_identity']}/messages",
        headers=_headers(credentials["usr_identity"]), json={"message": "How do you compare meal prices now?"},
    )
    assert reply.status_code == 200
    async with state.identity.sessions() as session:
        persona = await session.get(Personas, "security-shared-persona")
        conversation = await session.get(Conversations, conversations["usr_identity"])
        assert persona.owner_id == "usr_system_holder"
        assert conversation.user_id == "usr_identity"
        turn = await session.scalar(select(ConversationTurns).where(
            ConversationTurns.conversation_id == conversation.id, ConversationTurns.turn_number == 4,
        ))
        audit_ids = turn.metadata_json["retrieved_memory_ids"]
        assert audit_ids
        audited = list(await session.scalars(select(MemoryItems).where(MemoryItems.id.in_(audit_ids))))
        assert len(audited) == len(audit_ids)
        assert all(record.owner_id == "usr_identity" for record in audited)
    assert [context.owner_user_id for context in state.contexts] == [
        "usr_identity", "usr_other", "usr_identity", "usr_identity",
    ]
    assert all(context.data_classification == "private" for context in state.contexts)
    assert get_llm_request_context() is None


@pytest.mark.parametrize("action", ["logout", "reset"])
async def test_revoked_session_cannot_read_retained_private_memory(memory_identity_state, action):
    state = memory_identity_state
    client = state.identity.client
    first = await _signin(client)
    independent = await _signin(client)
    record = await state.memory.remember(
        "security-shared-persona", "Private memory retained after revocation.", owner_id="usr_identity",
    )
    path = "/api/personas/security-shared-persona/memories"
    assert (await client.get(path, headers=_headers(first))).status_code == 200
    assert (await client.get(path, params={"token": first["access_token"]})).status_code == 401
    if action == "logout":
        revoked = await client.post("/api/auth/logout", headers=_headers(first))
    else:
        requested = await client.post("/api/auth/forgot-password", json={"email": "owner@example.test"})
        assert requested.status_code == 200
        revoked = await client.post("/api/auth/reset-password", json={
            "email": "owner@example.test", "otp": state.identity.reset_mail.call_args.args[1],
            "password": "Replacement123!",
        })
    assert revoked.status_code == 200
    assert (await client.get(path, headers=_headers(first))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await client.get(path, headers=_headers(independent))).status_code == (200 if action == "logout" else 401)
    current = await _signin(client, password="Identity123!" if action == "logout" else "Replacement123!")
    readable = await client.get(path, headers=_headers(current))
    assert readable.status_code == 200
    assert [item["id"] for item in readable.json()] == [record.id]
    assert state.adapter.requests == []


@pytest.mark.parametrize("role", ["developer", "admin"])
async def test_operational_role_does_not_grant_another_owners_private_memory(memory_identity_state, role):
    state = memory_identity_state
    client = state.identity.client
    state.identity.app.include_router(routes.router, prefix="/api")
    owner = await _signin(client)
    operator = await _signin(client, "other@example.test")
    created = await client.post("/api/conversations", headers=_headers(owner), json={
        "persona_id": "security-shared-persona", "objective": "Private owner-only research.",
    })
    assert created.status_code == 201
    await state.memory.remember(
        "security-shared-persona", "Private memory is not operational metadata.",
        conversation_id=created.json()["id"],
    )
    async with state.identity.sessions() as session:
        user = await session.get(Users, "usr_other")
        user.role = role
        await session.commit()

    supplied = {**_headers(operator), "X-User-ID": "usr_identity", "X-Role": "admin"}
    assert (await client.get("/api/routes/status", headers=supplied)).status_code == 200
    memories = await client.get("/api/personas/security-shared-persona/memories", headers=supplied)
    assert memories.status_code == 200
    assert memories.json() == []
    assert (await client.get(f"/api/conversations/{created.json()['id']}", headers=supplied)).status_code == 404
    assert state.adapter.requests == []


@pytest.mark.parametrize("failure", ["database", "cancellation"])
async def test_reflection_rolls_back_all_insights_after_later_sql_failure(memory_identity_state, failure):
    state = memory_identity_state
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="atomic-reflection"),
        reply='{"insights":["First complete reflection.","Second complete reflection."]}',
    )])
    memory = MemoryService(state.identity.sessions, HashEmbedding(), llm=SingleAdapterLLMService(adapter))
    for index in range(8):
        await memory.remember("security-shared-persona", f"Private synthetic observation {index}.", owner_id="usr_identity")
    async with state.identity.sessions() as session:
        database = session.get_bind()

    def fail_second_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO memory_items") and "Second complete reflection." in parameters:
            if failure == "cancellation":
                raise asyncio.CancelledError()
            raise OperationalError(statement, None, RuntimeError("Synthetic storage failure"))

    event.listen(database, "before_cursor_execute", fail_second_insert)
    try:
        with pytest.raises(asyncio.CancelledError if failure == "cancellation" else OperationalError):
            await memory.reflect("security-shared-persona", owner_id="usr_identity")
    finally:
        event.remove(database, "before_cursor_execute", fail_second_insert)
    assert await memory.list_for_persona("security-shared-persona", kind="reflection", owner_id="usr_identity") == []