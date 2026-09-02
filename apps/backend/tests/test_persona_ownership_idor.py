"""Zero-trust IDOR and multi-tenant isolation tests for synthetic persona endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, MarketSegments, PersonaGenerationRuns, Personas, Studies
from bebshax.main import app


@pytest.mark.asyncio
async def test_persona_endpoints_idor_protection():
    """Verify strict user-scoped persona access and IDOR protection."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    # 1. Create User A and User B
    async with session_maker() as session:
        user_a = Users(
            id="usr_persona_a",
            email="persona_a@bebshax.ai",
            full_name="User A",
            hashed_password="pw_hash_a",
        )
        user_b = Users(
            id="usr_persona_b",
            email="persona_b@bebshax.ai",
            full_name="User B",
            hashed_password="pw_hash_b",
        )
        session.add_all([user_a, user_b])

        # 2. Create Study owned by User A
        study_a = Studies(
            id="std_persona_owned_by_a",
            user_id=user_a.id,
            title="User A Study",
            status="active",
            step=2,
        )
        session.add(study_a)

        # 3. Create Market Segment for Study A
        seg_a = MarketSegments(
            id="seg_study_a_1",
            study_id=study_a.id,
            user_id=user_a.id,
            segmentation_run_id="srun_a_1",
            name="Student Planners",
            cluster_label="cluster_0",
            description="Exam preppers",
            population_count=100,
            population_percentage=100.0,
            characteristics={"demographics": {"age_range": [19, 22]}},
        )
        session.add(seg_a)

        # 4. Create Persona Run and Persona for Study A
        run_a = PersonaGenerationRuns(
            id="pgen_a_1",
            study_id=study_a.id,
            user_id=user_a.id,
            segmentation_run_id="srun_a_1",
            status="completed",
            target_count=1,
            generated_count=1,
        )
        persona_a = Personas(
            id="per_a_1",
            study_id=study_a.id,
            user_id=user_a.id,
            owner_id=user_a.id,
            segment_id=seg_a.id,
            generation_run_id=run_a.id,
            name="Tanvir Ahmed",
            status="ready",
            grounding_score=0.92,
        )
        session.add_all([run_a, persona_a])
        await session.commit()

    # Generate Auth tokens
    token_a = create_access_token({"sub": user_a.id, "email": user_a.email})
    token_b = create_access_token({"sub": user_b.id, "email": user_b.email})
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_a = {"Authorization": f"Bearer {token_a}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # User B attempts to access User A's personas -> 404
        r_list = await ac.get(f"/api/studies/{study_a.id}/personas", headers=headers_b)
        assert r_list.status_code == 404

        # User B attempts to get User A's specific persona -> 404
        r_get = await ac.get(f"/api/studies/{study_a.id}/personas/{persona_a.id}", headers=headers_b)
        assert r_get.status_code == 404

        # User B attempts to generate personas in User A's study -> 404
        r_gen = await ac.post(
            f"/api/studies/{study_a.id}/personas/generate",
            json={"target_count": 2, "distribution_strategy": "equal"},
            headers=headers_b,
        )
        assert r_gen.status_code == 404

        # User B attempts to list User A's persona runs -> 404
        r_runs = await ac.get(f"/api/studies/{study_a.id}/persona-runs", headers=headers_b)
        assert r_runs.status_code == 404

        # User B attempts to delete User A's persona run -> 404
        r_del = await ac.delete(f"/api/studies/{study_a.id}/persona-runs/{run_a.id}", headers=headers_b)
        assert r_del.status_code == 404

        # User A legitimate access succeeds -> 200
        r_legit = await ac.get(f"/api/studies/{study_a.id}/personas", headers=headers_a)
        assert r_legit.status_code == 200
        data = r_legit.json()
        assert data["total"] == 1
        assert data["personas"][0]["name"] == "Tanvir Ahmed"


@pytest.mark.asyncio
async def test_demo_study_personas_are_listed_for_every_reader():
    """The seeded demo persona is stamped with the demo owner's user_id; the
    list endpoint used to also scope by the READER's id, so a judge signed in
    under their own account saw 0 personas in a demo whose card claims 1."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    async with session_maker() as session:
        session.add_all(
            [
                Users(
                    id="usr_demo_owner",
                    email="demo-owner@bebshax.ai",
                    full_name="Demo Owner",
                    hashed_password="hash",
                ),
                Users(
                    id="usr_demo_reader",
                    email="demo-reader@bebshax.ai",
                    full_name="Demo Reader",
                    hashed_password="hash",
                ),
                Studies(
                    id="std_demo_pub",
                    user_id="usr_demo_owner",
                    title="Public Demo Study",
                    status="completed",
                    is_demo=True,
                    persona_count=1,
                    persona_ids=["per_demo_pub"],
                ),
                Personas(
                    id="per_demo_pub",
                    study_id="std_demo_pub",
                    user_id="usr_demo_owner",
                    owner_id="usr_demo_owner",
                    name="Demo Persona",
                ),
            ]
        )
        await session.commit()

    reader_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': 'usr_demo_reader'})}"
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # A signed-in NON-owner and an anonymous caller both see the demo persona.
        for headers in (reader_headers, None):
            r_list = await ac.get("/api/studies/std_demo_pub/personas", headers=headers)
            assert r_list.status_code == 200
            body = r_list.json()
            assert body["total"] == 1
            assert [p["id"] for p in body["personas"]] == ["per_demo_pub"]

            r_get = await ac.get(
                "/api/studies/std_demo_pub/personas/per_demo_pub", headers=headers
            )
            assert r_get.status_code == 200
            assert r_get.json()["id"] == "per_demo_pub"

    await engine.dispose()
