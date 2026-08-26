"""API happy-path tests: full app lifespan against a file-backed sqlite DB,
with the persona engine swapped for a fake-backed one after startup."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

import bebshax.persona.orm  # noqa: F401
from bebshax.config import get_settings
from bebshax.db.models import Base
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.persona.generation import PersonaEngine


@pytest.fixture
async def app_client(tmp_path, monkeypatch, evidence_store, persona_json):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    from bebshax.main import create_app

    app = create_app()
    with TestClient(app) as client:
        adapter = FakeAdapter(
            [
                FakeRoute(
                    candidate=RouteCandidate(provider="fake", model="m1"),
                    replies=[persona_json()],
                )
            ]
        )
        app.state.persona_engine = PersonaEngine(
            SingleAdapterLLMService(adapter), evidence_store
        )
        # Seed test user for auth
        from bebshax.auth.models import Users
        from bebshax.auth.security import create_access_token
        user_id = "usr_test_fixture"
        async with app.state.db_sessionmaker() as session:
            existing = await session.get(Users, user_id)
            if not existing:
                session.add(Users(
                    id=user_id,
                    email="fixture@test.local",
                    full_name="Test Fixture User",
                    auth_provider="email",
                    is_active=True,
                    is_verified=True,
                ))
                await session.commit()
        headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
        yield client, headers
    get_settings.cache_clear()


async def test_full_persona_flow_over_http(app_client) -> None:
    client, headers = app_client
    created = client.post(
        "/api/businesses", json={"name": "QuickBite", "description": "Food delivery in Dhaka"},
        headers=headers,
    )
    assert created.status_code == 201
    business_id = created.json()["id"]

    listed = client.get("/api/businesses", headers=headers)
    assert any(b["id"] == business_id for b in listed.json())

    generated = client.post(f"/api/businesses/{business_id}/personas", json={}, headers=headers)
    assert generated.status_code == 201, generated.text
    persona = generated.json()
    assert persona["name"] == "Rina Akter"
    assert all("provenance_class" in a for a in persona["attributes"])

    fetched = client.get(f"/api/personas/{persona['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["occupation"] == "university student"


async def test_unknown_business_and_persona_return_404(app_client) -> None:
    client, headers = app_client
    assert client.post("/api/businesses/nope/personas", json={}, headers=headers).status_code == 404
    assert client.get("/api/personas/nope").status_code == 404

