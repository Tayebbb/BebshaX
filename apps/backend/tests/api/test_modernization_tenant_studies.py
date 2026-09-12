"""Tenant authorization and canonical study-state regressions."""

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm.exc import StaleDataError

from bebshax.api.limiter import limiter
from bebshax.api.routes import router as routing_router
from bebshax.api.studies import router
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, LLMRequests, Personas, SavedAudiences, Studies
from bebshax.llm.types import TaskType


@pytest.fixture
async def tenant_api(tmp_path) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(Users(
            id="tenant_owner", email="tenant@example.test", full_name="Tenant Owner",
            auth_provider="email", is_active=True, is_verified=True,
        ))
        await session.commit()
    app = FastAPI()
    app.state.db_sessionmaker = sessions
    app.state.limiter = limiter
    app.state.settings = SimpleNamespace(environment="production")
    app.include_router(router, prefix="/api")
    app.include_router(routing_router, prefix="/api")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, sessions
    finally:
        await engine.dispose()


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('tenant_owner')}"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
async def test_create_requires_authentication_before_writing(tenant_api, headers) -> None:
    client, sessions = tenant_api
    response = await client.post("/api/studies", json={"title": "Private research"}, headers=headers)
    async with sessions() as session:
        count = await session.scalar(select(func.count()).select_from(Studies))
    assert (response.status_code, count) == (401, 0)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
async def test_saved_audience_requires_authentication_before_writing(tenant_api, headers) -> None:
    client, sessions = tenant_api
    response = await client.post(
        "/api/audiences", json={"id": "aud_probe", "name": "Probe", "persona_ids": []}, headers=headers,
    )
    async with sessions() as session:
        count = await session.scalar(select(func.count()).select_from(SavedAudiences))
    assert (response.status_code, count) == (401, 0)


async def test_saved_audience_owner_comes_from_token_not_payload(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    response = await client.post(
        "/api/audiences", json={"name": "Mine", "user_id": "someone_else", "persona_ids": []},
        headers=tenant_headers,
    )
    assert response.status_code == 201
    async with sessions() as session:
        audience = await session.get(SavedAudiences, response.json()["id"])
    assert audience is not None and audience.user_id == "tenant_owner"


@pytest.mark.parametrize("method", ["patch", "put"])
async def test_update_missing_study_does_not_create(tenant_api, tenant_headers, method) -> None:
    client, sessions = tenant_api
    response = await client.request(
        method, "/api/studies/missing", json={"title": "Not a create"}, headers=tenant_headers,
    )
    async with sessions() as session:
        assert await session.get(Studies, "missing") is None
    assert response.status_code == 404


async def test_create_ignores_legacy_derived_fields_and_client_identity(tenant_api, tenant_headers) -> None:
    client, _sessions = tenant_api
    response = await client.post("/api/studies", headers=tenant_headers, json={
        "id": "client-chosen", "user_id": "another-owner", "title": "Research",
        "persona_count": 5, "persona_ids": ["foreign"], "personas_data": [{"id": "foreign"}],
        "findings": {"invented": "evidence"}, "is_demo": True,
    })
    assert response.status_code == 201
    study = response.json()
    assert study["id"] != "client-chosen"
    assert study["user_id"] == "tenant_owner"
    assert study["is_demo"] is False
    assert (study["persona_count"], study["persona_ids"], study["personas_data"], study["findings"]) == (0, [], [], None)
    assert study["revision"] == 1
    assert response.headers["etag"] == '"1"'


async def test_study_reads_and_legacy_updates_use_canonical_owned_personas(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add(Studies(
            id="canonical", user_id="tenant_owner", title="Canonical", persona_count=99,
            persona_ids=["injected"], personas_data=[{"id": "injected"}],
            findings={"generated": "retained"},
        ))
        session.add_all([
            Personas(id="active", study_id="canonical", owner_id="tenant_owner", name="Active"),
            Personas(id="archived", study_id="canonical", owner_id="tenant_owner", name="Old", status="archived"),
            Personas(id="foreign", study_id="canonical", owner_id="another-owner", name="Foreign"),
        ])
        await session.commit()
    detail = await client.get("/api/studies/canonical", headers=tenant_headers)
    listing = await client.get("/api/studies", headers=tenant_headers)
    updated = await client.patch("/api/studies/canonical", headers=tenant_headers, json={
        "title": "Updated", "persona_count": 777, "persona_ids": ["foreign"],
        "personas_data": [{"id": "foreign"}], "findings": {"invented": "replacement"},
    })
    assert updated.status_code == 200
    for study in (detail.json(), listing.json()[0], updated.json()):
        assert study["persona_count"] == 1
        assert study["persona_ids"] == ["active"]
        assert [persona["id"] for persona in study["personas_data"]] == ["active"]
        assert study["findings"] == {"generated": "retained"}
    async with sessions() as session:
        study = await session.get(Studies, "canonical")
        assert study.persona_count == 1
        assert study.persona_ids == ["active"]
        assert [persona["id"] for persona in study.personas_data] == ["active"]


async def test_stale_full_history_update_preserves_winning_revision(tenant_api, tenant_headers) -> None:
    client, _sessions = tenant_api
    created = (await client.post("/api/studies", headers=tenant_headers, json={"title": "CAS"})).json()
    url = f"/api/studies/{created['id']}"
    history = [{"role": "user", "content": "First"}, {"role": "assistant", "content": "Reply"}]
    accepted = await client.patch(url, headers=tenant_headers, json={
        "expected_revision": 1, "copilot_messages": history,
    })
    rejected = await client.patch(url, headers=tenant_headers, json={
        "expected_revision": 1, "copilot_messages": [{"role": "user", "content": "Stale tab"}],
    })
    assert accepted.status_code == 200
    assert accepted.json()["revision"] == 2
    assert rejected.status_code == 409
    stored = await client.get(url, headers=tenant_headers)
    assert stored.json()["copilot_messages"] == history
    assert stored.headers["etag"] == '"2"'


@pytest.mark.parametrize("stale_history", [[], [{"role": "user", "content": "First"}], [
    {"role": "user", "content": "Different tab"}, {"role": "assistant", "content": "Different reply"},
]])
async def test_legacy_history_cannot_erase_or_replace_newer_messages(
    tenant_api, tenant_headers, stale_history,
) -> None:
    client, _sessions = tenant_api
    created = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Legacy history"})).json()
    url = f"/api/studies/{created['id']}"
    history = [{"role": "user", "content": "First"}, {"role": "assistant", "content": "Reply"}]
    accepted = await client.patch(url, headers=tenant_headers, json={"copilot_messages": history})
    assert accepted.status_code == 200
    rejected = await client.patch(url, headers=tenant_headers, json={"copilot_messages": stale_history})
    assert rejected.status_code == 409
    stored = await client.get(url, headers=tenant_headers)
    assert stored.json()["copilot_messages"] == history
    assert stored.json()["revision"] == accepted.json()["revision"]


async def test_legacy_history_can_append_without_supplying_a_revision(tenant_api, tenant_headers) -> None:
    client, _sessions = tenant_api
    created = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Compatible history"})).json()
    url = f"/api/studies/{created['id']}"
    history = [{"role": "user", "content": "First"}]
    assert (await client.patch(url, headers=tenant_headers, json={"copilot_messages": history})).status_code == 200
    history.append({"role": "assistant", "content": "Reply"})
    response = await client.patch(url, headers=tenant_headers, json={"copilot_messages": history})
    assert response.status_code == 200
    assert response.json()["copilot_messages"] == history


@pytest.mark.parametrize("condition,status_code", [('"0"', 400), ('W/"1"', 400), ('"1", "2"', 400), ('"2"', 412)])
async def test_if_match_rejects_invalid_or_stale_revision(tenant_api, tenant_headers, condition, status_code) -> None:
    client, _sessions = tenant_api
    created = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Original"})).json()
    response = await client.patch(f"/api/studies/{created['id']}", json={"title": "Changed"}, headers={
        **tenant_headers, "If-Match": condition,
    })
    assert response.status_code == status_code
    stored = await client.get(f"/api/studies/{created['id']}", headers=tenant_headers)
    assert stored.json()["title"] == "Original"


@pytest.mark.parametrize("field,value", [("persona_count", 9), ("persona_ids", []), ("personas_data", []), ("findings", {})])
async def test_guarded_clients_cannot_submit_derived_state(tenant_api, tenant_headers, field, value) -> None:
    client, _sessions = tenant_api
    created = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Guarded"})).json()
    response = await client.patch(f"/api/studies/{created['id']}", headers=tenant_headers, json={
        "expected_revision": 1, field: value,
    })
    assert response.status_code == 422


async def test_demo_is_publicly_readable_but_not_writable(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add(Studies(id="public-demo", user_id="demo-owner", title="Demo", is_demo=True))
        await session.commit()
    assert (await client.get("/api/studies/public-demo")).status_code == 200
    for headers in ({}, tenant_headers):
        response = await client.patch("/api/studies/public-demo", headers=headers, json={"title": "Changed"})
        assert response.status_code == 403


async def test_anonymous_study_list_excludes_ambiguous_legacy_owners(tenant_api) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add_all([
            Studies(id="unknown-owner", user_id=None, title="Private legacy research", prompt="Unattributed private context"),
            Studies(id="system-owner", user_id="usr_system_holder", title="Legacy system research"),
            Studies(id="explicit-demo", user_id="demo-owner", title="Public demo", is_demo=True),
        ])
        await session.commit()
    response = await client.get("/api/studies")
    assert response.status_code == 200
    assert [study["id"] for study in response.json()] == ["explicit-demo"]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
async def test_provenance_requires_authentication(tenant_api, headers) -> None:
    client, _sessions = tenant_api
    response = await client.get("/api/provenance", headers=headers)
    assert response.status_code == 401


async def test_unknown_provenance_never_becomes_public_or_inherits_persona_owner(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add(Personas(id="linked-persona", owner_id="tenant_owner", name="Linked"))
        session.add_all([
            LLMRequests(request_id="orphan", persona_id="deleted-persona", task=TaskType.PERSONA_INTERVIEW),
            LLMRequests(request_id="infrastructure", task=TaskType.PERSONA_INTERVIEW),
            LLMRequests(request_id="historical", persona_id="linked-persona", task=TaskType.PERSONA_INTERVIEW),
        ])
        await session.commit()
    response = await client.get("/api/provenance", headers=tenant_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


async def test_provenance_owner_is_independent_of_mutable_persona_link(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add(Personas(id="reassigned", owner_id="another-owner", name="Changed owner"))
        session.add_all([
            LLMRequests(
                request_id="owned", owner_id="tenant_owner", persona_id="reassigned", task=TaskType.PERSONA_INTERVIEW,
                attempts=[{"failure_kind": "timeout", "failure_detail": "private provider echo"}],
            ),
            LLMRequests(request_id="foreign", owner_id="another-owner", task=TaskType.PERSONA_INTERVIEW),
        ])
        await session.commit()
    response = await client.get("/api/provenance", headers=tenant_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["request_id"] for item in response.json()["items"]] == ["owned"]
    assert response.json()["items"][0]["attempts"][0]["failure_detail"] is None
    async with sessions() as session:
        await session.delete(await session.get(Personas, "reassigned"))
        await session.commit()
    assert (await client.get("/api/provenance", headers=tenant_headers)).json()["total"] == 1


async def test_provenance_owner_cannot_be_reassigned(tenant_api) -> None:
    _client, sessions = tenant_api
    async with sessions() as session:
        session.add(LLMRequests(request_id="immutable", owner_id="tenant_owner", task=TaskType.PERSONA_INTERVIEW))
        await session.commit()
        row = await session.get(LLMRequests, "immutable")
        with pytest.raises(ValueError, match="immutable"):
            row.owner_id = "another-owner"
            await session.flush()
        await session.rollback()


@pytest.mark.parametrize("path", ["/api/routes/status", "/api/routing/capacity"])
async def test_diagnostics_production_gate_cannot_be_spoofed(tenant_api, tenant_headers, path) -> None:
    client, _sessions = tenant_api
    response = await client.get(path + "?role=admin&environment=development", headers={
        **tenant_headers, "X-Role": "admin", "X-Forwarded-For": "127.0.0.1",
    })
    assert response.status_code == 404


async def test_two_loaded_sessions_cannot_commit_the_same_revision(tenant_api) -> None:
    _client, sessions = tenant_api
    async with sessions() as session:
        session.add(Studies(id="racing-study", user_id="tenant_owner", title="Original"))
        await session.commit()
    async with sessions() as first, sessions() as second:
        first_study = await first.get(Studies, "racing-study")
        second_study = await second.get(Studies, "racing-study")
        first_study.title = "Accepted writer"
        second_study.title = "Stale writer"
        await first.commit()
        with pytest.raises(StaleDataError):
            await second.commit()
        await second.rollback()
    async with sessions() as session:
        study = await session.get(Studies, "racing-study")
        assert (study.title, study.revision) == ("Accepted writer", 2)


async def test_shared_demo_is_read_only_even_for_matching_owner(tenant_api, tenant_headers) -> None:
    client, sessions = tenant_api
    async with sessions() as session:
        session.add(Studies(id="owned-demo", user_id="tenant_owner", title="Seeded demo", is_demo=True))
        await session.commit()
    response = await client.patch("/api/studies/owned-demo", headers=tenant_headers, json={"title": "Changed"})
    assert response.status_code == 403


async def test_extremely_long_revision_header_is_rejected_without_conversion_error(tenant_api, tenant_headers) -> None:
    client, _sessions = tenant_api
    study = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Bounded"})).json()
    response = await client.patch(f"/api/studies/{study['id']}", headers={
        **tenant_headers, "If-Match": '"' + "1" * 5000 + '"',
    }, json={"title": "Not accepted"})
    assert response.status_code == 400


async def test_valid_if_match_is_honored_and_conflicting_body_revision_is_rejected(tenant_api, tenant_headers) -> None:
    client, _sessions = tenant_api
    study = (await client.post("/api/studies", headers=tenant_headers, json={"title": "Header guarded"})).json()
    url = f"/api/studies/{study['id']}"
    accepted = await client.patch(url, headers={**tenant_headers, "If-Match": '"1"'}, json={"title": "Accepted"})
    assert accepted.status_code == 200
    assert accepted.json()["revision"] == 2
    disagreement = await client.patch(url, headers={**tenant_headers, "If-Match": '"2"'}, json={
        "expected_revision": 1, "title": "Rejected",
    })
    assert disagreement.status_code == 400


@pytest.mark.parametrize("environment,peer,expected_status", [
    ("development", "127.0.0.1", 200), ("development", "192.0.2.10", 404), ("staging", "127.0.0.1", 404),
])
async def test_diagnostics_require_development_and_actual_local_peer(
    tmp_path, environment, peer, expected_status,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'diagnostics.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(Users(
            id="diag_dev", email="dev@example.test", full_name="Developer", role="developer",
            auth_provider="email", is_active=True, is_verified=True,
        ))
        await session.commit()
    app = FastAPI()
    app.state.db_sessionmaker = sessions
    app.state.settings = SimpleNamespace(environment=environment)
    app.state.llm_adapters = {}
    app.include_router(routing_router, prefix="/api")
    # Only the success case presents credentials: the 404 answers must not depend on any token.
    headers = {"X-Forwarded-For": "127.0.0.1"}
    if expected_status == 200:
        headers["Authorization"] = f"Bearer {create_access_token('diag_dev')}"
    try:
        async with AsyncClient(transport=ASGITransport(app=app, client=(peer, 1234)), base_url="http://test") as client:
            response = await client.get("/api/routing/capacity", headers=headers)
    finally:
        await engine.dispose()
    assert response.status_code == expected_status


async def test_development_diagnostics_still_require_a_developer(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'diagnostics_role.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(Users(
            id="diag_user", email="user@example.test", full_name="Plain User",
            auth_provider="email", is_active=True, is_verified=True,
        ))
        await session.commit()
    app = FastAPI()
    app.state.db_sessionmaker = sessions
    app.state.settings = SimpleNamespace(environment="development")
    app.state.llm_adapters = {}
    app.include_router(routing_router, prefix="/api")
    try:
        async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 1234)), base_url="http://test") as client:
            anonymous = await client.get("/api/routing/capacity")
            plain = await client.get(
                "/api/routing/capacity", headers={"Authorization": f"Bearer {create_access_token('diag_user')}"},
            )
    finally:
        await engine.dispose()
    assert (anonymous.status_code, plain.status_code) == (401, 403)