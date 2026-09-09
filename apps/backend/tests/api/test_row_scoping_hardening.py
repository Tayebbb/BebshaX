"""Row-scoping hardening regression tests (B6 stage 3 — API row-scoping).

Covers the gaps closed after the tenancy audit: anonymous callers must never
read or mutate another tenant's rows. The rule everywhere is the canonical
`_user_owns_study` / `_owner_accessible` policy from api/studies.py:
demo/system/anonymous-tenant rows are shared; owned rows require their owner.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import (
    Base,
    DatasetSources,
    LLMRequests,
    Personas,
    SavedAudiences,
    Studies,
)
from bebshax.interview.engine import InterviewEngine
from bebshax.interview.orm import Conversations
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.types import TaskType


@pytest.fixture
async def scoped_app(tmp_path):
    """App over sqlite with one owned tenant (usr_owner) and shared rows."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'row_scoping.db'}"
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        session.add_all(
            [
                Users(id="usr_owner", email="owner@example.com", hashed_password="x", full_name="Owner"),
                Users(id="usr_other", email="other@example.com", hashed_password="x", full_name="Other"),
                Studies(id="std_owned", user_id="usr_owner", title="Owned Study", status="in_progress"),
                Personas(
                    id="per_owned", study_id="std_owned", user_id="usr_owner",
                    owner_id="usr_owner", name="Private Persona", version=1,
                ),
                Personas(id="per_shared", owner_id="usr_system_holder", name="Shared Persona", version=1),
                Conversations(
                    id="conv_owned", study_id="std_owned", user_id="usr_owner",
                    persona_id="per_owned", objective="Private objective", status="active",
                ),
                DatasetSources(id="ds_owned", user_id="usr_owner", name="Owned Dataset", status="ready"),
                DatasetSources(id="ds_shared", user_id=None, name="Shared Dataset", status="ready"),
                DatasetSources(
                    id="ds_imported", user_id="usr_default", name="Anon Import", status="ready",
                    source_type="url", source_url="https://example.com/data.csv",
                ),
                DatasetSources(
                    id="ds_owned_url", user_id="usr_owner", name="Owned URL Dataset", status="ready",
                    source_type="url", source_url="https://example.com/private.csv",
                ),
                SavedAudiences(id="aud_owned", user_id="usr_owner", name="Owned Audience"),
                SavedAudiences(id="aud_shared", user_id=None, name="Shared Audience"),
                LLMRequests(request_id="req_owned", task=TaskType.PERSONA_RESPONSE, persona_id="per_owned", success=True),
                LLMRequests(request_id="req_infra", task=TaskType.EMERGENCY_FALLBACK, persona_id=None, success=True),
            ]
        )
        await session.commit()
    await engine.dispose()

    from bebshax.main import create_app

    app = create_app()
    app.state.db_sessionmaker = maker
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=["Hi there."] * 10)]
    )
    app.state.interview_engine = InterviewEngine(
        SingleAdapterLLMService(adapter), maker, memory=getattr(app.state, "memory_service", None)
    )
    return app, maker


def _owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'usr_owner', 'email': 'owner@example.com'})}"}


@pytest.mark.asyncio
async def test_anonymous_cannot_see_or_delete_owned_dataset(scoped_app):
    app, maker = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/datasets")
        ids = [d["id"] for d in listed.json()]
        assert "ds_shared" in ids and "ds_owned" not in ids
        # anonymous-tenant stamps (e.g. candidate imports write "usr_default")
        # stay visible to everyone — they are shared-pool rows
        assert "ds_imported" in ids

        assert (await client.get("/api/datasets/ds_owned")).status_code == 404
        assert (await client.delete("/api/datasets/ds_owned")).status_code == 404
        # refresh must respect the same tenant filter (read+mutate bypass)
        assert (await client.post("/api/datasets/ds_owned_url/refresh")).status_code == 404

        # owner still sees and can delete their row
        assert (await client.get("/api/datasets/ds_owned", headers=_owner_headers())).status_code == 200
        assert (await client.delete("/api/datasets/ds_owned", headers=_owner_headers())).status_code == 200
    async with maker() as session:
        assert await session.get(DatasetSources, "ds_shared") is not None
        assert await session.get(DatasetSources, "ds_owned_url") is not None


@pytest.mark.asyncio
async def test_anonymous_cannot_see_or_delete_owned_audience(scoped_app):
    app, maker = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/api/audiences")
        ids = [a["id"] for a in listed.json()]
        assert "aud_shared" in ids and "aud_owned" not in ids

        assert (await client.delete("/api/audiences/aud_owned")).status_code == 404
        assert (await client.delete("/api/audiences/aud_owned", headers=_owner_headers())).status_code == 200
        # Shared-pool rows are READABLE by everyone but destroyable by nobody:
        # an anonymous caller deleting them is exactly the cross-user
        # destruction the write gate exists to stop.
        assert (await client.delete("/api/audiences/aud_shared")).status_code == 404
    async with maker() as session:
        assert await session.get(SavedAudiences, "aud_owned") is None
        assert await session.get(SavedAudiences, "aud_shared") is not None


@pytest.mark.asyncio
async def test_study_identity_comes_from_token_not_payload(scoped_app):
    app, _ = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # anonymous create with a spoofed user_id lands in the anonymous tenant
        res = await client.post(
            "/api/studies",
            json={"prompt": "spoof attempt", "user_id": "usr_owner"},
        )
        assert res.status_code == 201
        assert res.json()["user_id"] == "usr_default"

        # anonymous list ignores ?user_id= impersonation
        listed = await client.get("/api/studies", params={"user_id": "usr_owner"})
        assert "std_owned" not in [s["id"] for s in listed.json()]

        # authenticated create ignores a foreign payload user_id
        res_auth = await client.post(
            "/api/studies",
            json={"prompt": "own study", "user_id": "usr_other"},
            headers=_owner_headers(),
        )
        assert res_auth.json()["user_id"] == "usr_owner"

        # PATCH on an existing study can never re-attach it to another tenant
        patched = await client.patch(
            "/api/studies/std_owned",
            json={"status": "in_progress", "user_id": "usr_other"},
            headers=_owner_headers(),
        )
        assert patched.status_code == 200
        assert patched.json()["user_id"] == "usr_owner"


@pytest.mark.asyncio
async def test_segmentation_endpoints_reject_anonymous_on_owned_study(scoped_app):
    app, _ = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        anon = await client.get("/api/studies/std_owned/segmentation/readiness")
        assert anon.status_code == 404
        owner = await client.get("/api/studies/std_owned/segmentation/readiness", headers=_owner_headers())
        assert owner.status_code == 200


@pytest.mark.asyncio
async def test_legacy_conversation_endpoints_are_owner_scoped(scoped_app):
    app, _ = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/conversations/conv_owned")).status_code == 404
        assert (
            await client.post("/api/conversations/conv_owned/messages", json={"message": "probe"})
        ).status_code == 404
        assert (
            await client.post("/api/personas/per_owned/conversations", json={"objective": "probe"})
        ).status_code == 404
        assert (
            await client.post("/api/conversations", json={"persona_id": "per_owned", "objective": "probe"})
        ).status_code == 404

        # Shared transcripts remain readable; new conversations require a private owner.
        assert (await client.get("/api/conversations/conv_owned", headers=_owner_headers())).status_code == 200
        anonymous = await client.post(
            "/api/conversations", json={"persona_id": "per_shared", "objective": "ok"}
        )
        assert anonymous.status_code == 403
        shared = await client.post(
            "/api/conversations", json={"persona_id": "per_shared", "objective": "ok"},
            headers=_owner_headers(),
        )
        assert shared.status_code == 201


@pytest.mark.asyncio
async def test_persona_read_and_memories_are_owner_scoped(scoped_app):
    app, _ = scoped_app

    class _FakeMemoryService:
        async def list_for_persona(self, persona_id, kind=None, limit=50, *, sources=("persona",)):
            return []

    app.state.memory_service = _FakeMemoryService()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/personas/per_owned")).status_code == 404
        assert (await client.get("/api/personas/per_shared")).status_code == 200
        assert (await client.get("/api/personas/per_owned/memories")).status_code == 404
        assert (await client.get("/api/personas/per_owned", headers=_owner_headers())).status_code == 200
        # owner reaches their memories (empty here — the gate lets them through)
        owner_mem = await client.get("/api/personas/per_owned/memories", headers=_owner_headers())
        assert owner_mem.status_code == 200
        assert owner_mem.json() == []


@pytest.mark.asyncio
async def test_copilot_generate_personas_refuses_foreign_study(scoped_app):
    app, maker = scoped_app
    app.state.llm_router = None  # skeleton path — the gate must fire first
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/study/generate-personas",
            json={"study_prompt": "probe", "roles": [], "study_id": "std_owned"},
        )
        # 401: the endpoint now requires a token, so an anonymous caller is
        # refused before the ownership gate is even reached.
        assert res.status_code in (401, 403, 404)
    async with maker() as session:
        rows = (await session.execute(select(Personas).where(Personas.study_id == "std_owned"))).scalars().all()
        assert [p.id for p in rows] == ["per_owned"]  # nothing injected


@pytest.mark.asyncio
async def test_provenance_hides_owned_persona_rows_from_anonymous(scoped_app):
    app, _ = scoped_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        anon = (await client.get("/api/provenance")).json()
        anon_ids = [i["request_id"] for i in anon["items"]]
        assert "req_infra" in anon_ids and "req_owned" not in anon_ids

        owner = (await client.get("/api/provenance", headers=_owner_headers())).json()
        owner_ids = [i["request_id"] for i in owner["items"]]
        assert "req_owned" in owner_ids and "req_infra" in owner_ids


@pytest.mark.asyncio
async def test_generate_under_foreign_business_requires_owner(scoped_app):
    app, maker = scoped_app
    async with maker() as session:
        from bebshax.db.models import Businesses

        session.add(Businesses(id="biz_owned", name="Private Biz", owner_id="usr_owner"))
        await session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # writes require auth (Sazid's B6 correction) — anonymous gets 401
        res = await client.post("/api/businesses/biz_owned/personas", json={"hints": "probe"})
        assert res.status_code == 401
        # an authenticated non-owner is still blocked by the owner gate
        other = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_other'})}"}
        res_other = await client.post(
            "/api/businesses/biz_owned/personas", json={"hints": "probe"}, headers=other
        )
        assert res_other.status_code == 404
