"""Interview HTTP API flow against the full app with a fake-backed engine."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bebshax.interview.orm  # noqa: F401
import bebshax.memory.orm  # noqa: F401
import bebshax.persona.orm  # noqa: F401
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.config import get_settings
from bebshax.db.models import Base
from bebshax.interview.engine import InterviewEngine
from bebshax.persona.schema import PersonaAttribute, PersonaProfile
from bebshax.persona.store import create_business, save_persona

# Continuing a conversation is an owner-only write (shared-pool rows are
# readable by everyone, writable by nobody), so the legacy flow signs in.
# Minted per call: jti-less tokens expire after ACCESS_LIFETIME (15 min), so
# an import-time token dies partway through a full-suite run.
def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'usr_interviewer'})}"}


@pytest.fixture
async def app_client(tmp_path, monkeypatch, llm_factory):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add(
            Users(
                id="usr_interviewer",
                email="interviewer@example.com",
                full_name="Interviewer",
                hashed_password="x",
                is_verified=True,
            )
        )
        business = await create_business(session, "QuickBite", "food delivery", owner_id="usr_system_holder")
        profile = PersonaProfile(
            business_id=business.id,
            name="Rina Akter",
            age=24,
            occupation="university student",
            location="Dhaka",
            income_range="stipend",
            education="BSc",
            description="desc",
            attributes=[PersonaAttribute(key="goal", value="cheap meals")],
        )
        await save_persona(session, profile, owner_id="usr_system_holder")
    await engine.dispose()

    from bebshax.main import create_app

    app = create_app()
    with TestClient(app) as client:
        llm, _ = llm_factory(["I'm Rina, nice to meet you!", "Late deliveries drive me crazy."])
        app.state.interview_engine = InterviewEngine(
            llm, app.state.db_sessionmaker, memory=app.state.memory_service
        )
        yield client, profile.id
    get_settings.cache_clear()


async def test_interview_http_flow(app_client) -> None:
    client, persona_id = app_client

    started = client.post(
        f"/api/personas/{persona_id}/conversations",
        json={"objective": "pain points"},
        headers=_headers(),
    )
    assert started.status_code == 201
    conversation_id = started.json()["id"]

    first = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "Who are you?"},
        headers=_headers(),
    )
    assert first.status_code == 200
    assert "Rina" in first.json()["reply"]

    second = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"message": "What bothers you about delivery apps?"},
        headers=_headers(),
    )
    assert second.status_code == 200

    transcript = client.get(f"/api/conversations/{conversation_id}", headers=_headers())
    assert transcript.status_code == 200
    turns = transcript.json()["turns"]
    assert len(turns) == 4
    assert [t["role"] for t in turns] == ["interviewer", "persona", "interviewer", "persona"]


async def test_unknown_ids_return_404(app_client) -> None:
    client, _ = app_client
    assert (
        client.post(
            "/api/personas/nope/conversations", json={"objective": "x"}, headers=_headers()
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/conversations/nope/messages", json={"message": "x"}, headers=_headers()
        ).status_code
        == 404
    )
    assert client.get("/api/conversations/nope", headers=_headers()).status_code == 404
