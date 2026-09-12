import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Studies
from bebshax.main import app
from bebshax.utils.title_generator import generate_deterministic_study_title


def test_deterministic_title_generator():
    # Conversational filler stripping
    t1 = generate_deterministic_study_title(
        "I'm building an AI study planner for university students in Bangladesh and it costs 250 BDT/month"
    )
    assert "AI Study Planner" in t1
    assert "for University Students" in t1
    assert "I'm building" not in t1

    # Acronyms preserved
    t2 = generate_deterministic_study_title("We want to test a B2B SaaS analytics tool for e-commerce")
    assert "B2B SaaS Analytics Tool" in t2
    assert "We want to" not in t2

    # Empty prompt fallback
    t3 = generate_deterministic_study_title("", study_type="interviews")
    assert t3 == "Customer Discovery & Workflow Study"

    t4 = generate_deterministic_study_title("   ", study_type="pricing")
    assert t4 == "Pricing Elasticity & WTP Analysis"

    # Truncation never leaves a dangling connective ("... Decants to Students at")
    t5 = generate_deterministic_study_title(
        "Selling authentic perfume decants to students at affordable prices with fast delivery"
    )
    assert not t5.split()[-1].lower() in {"at", "to", "for", "with", "the", "a", "an", "of", "in", "on", "by"}


@pytest.mark.asyncio
async def test_create_study_and_title_generation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker
    async with session_maker() as session:
        session.add(Users(
            id="usr_creator", email="creator@test.com", hashed_password="hash",
            full_name="Creator", is_active=True, is_verified=True,
        ))
        await session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_creator', 'email': 'creator@test.com'})}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create with prompt only -> deterministic title
        res = await client.post(
            "/api/studies",
            headers=headers,
            json={
                "prompt": "I'm developing an AI-powered pricing optimization engine for local grocery stores",
                "type": "pricing",
                "target_audience": "Local grocery store owners",
                "pricing_hypothesis": "৳1500/month flat fee",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["type"] == "pricing"
        assert "AI-Powered Pricing Optimization Engine" in data["title"]
        assert data["target_audience"] == "Local grocery store owners"
        assert data["pricing_hypothesis"] == "৳1500/month flat fee"
        study_id = data["id"]

        # 2. Get study
        get_res = await client.get(f"/api/studies/{study_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["id"] == study_id

        # 3. Reject empty study creation
        bad_res = await client.post("/api/studies", headers=headers, json={"prompt": "   ", "title": ""})
        assert bad_res.status_code == 400
        assert "Describe your product idea" in bad_res.json()["detail"]

        # 4. Anonymous callers cannot create private studies at all
        anon_res = await client.post("/api/studies", json={"prompt": "Anonymous idea"})
        assert anon_res.status_code == 401

    await engine.dispose()


@pytest.mark.asyncio
async def test_study_user_isolation_and_authorization():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    # Create Alice and Bob in users table (verified: unverified accounts cannot act)
    async with session_maker() as session:
        alice = Users(
            id="usr_alice", email="alice@test.com", hashed_password="hash", full_name="Alice",
            is_active=True, is_verified=True,
        )
        bob = Users(
            id="usr_bob", email="bob@test.com", hashed_password="hash", full_name="Bob",
            is_active=True, is_verified=True,
        )
        session.add_all([alice, bob])
        await session.commit()

    token_alice = create_access_token({"sub": "usr_alice", "email": "alice@test.com"})
    token_bob = create_access_token({"sub": "usr_bob", "email": "bob@test.com"})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Alice creates a study
        res_alice = await client.post(
            "/api/studies",
            headers={"Authorization": f"Bearer {token_alice}"},
            json={
                "prompt": "Fitness tracker with personalized streak motivation",
                "type": "interviews",
            },
        )
        assert res_alice.status_code == 201
        alice_study = res_alice.json()
        assert alice_study["user_id"] == "usr_alice"
        alice_study_id = alice_study["id"]

        # Alice can get her study
        res_get_alice = await client.get(
            f"/api/studies/{alice_study_id}",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert res_get_alice.status_code == 200

        # Bob cannot get Alice's study (404 Not Found for privacy)
        res_get_bob = await client.get(
            f"/api/studies/{alice_study_id}",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert res_get_bob.status_code == 404

        # Bob cannot modify Alice's study — 404, matching the read above:
        # a 403 here would confirm the hidden study exists.
        res_patch_bob = await client.patch(
            f"/api/studies/{alice_study_id}",
            headers={"Authorization": f"Bearer {token_bob}"},
            json={"title": "Hacked Title"},
        )
        assert res_patch_bob.status_code == 404

        # Bob cannot delete Alice's study — 404 for the same reason
        res_del_bob = await client.delete(
            f"/api/studies/{alice_study_id}",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert res_del_bob.status_code == 404

        # Alice's study list contains her study
        list_alice = await client.get(
            "/api/studies",
            headers={"Authorization": f"Bearer {token_alice}"},
        )
        assert list_alice.status_code == 200
        alice_study_ids = [s["id"] for s in list_alice.json()]
        assert alice_study_id in alice_study_ids

        # Bob's study list does NOT contain Alice's study
        list_bob = await client.get(
            "/api/studies",
            headers={"Authorization": f"Bearer {token_bob}"},
        )
        assert list_bob.status_code == 200
        bob_study_ids = [s["id"] for s in list_bob.json()]
        assert alice_study_id not in bob_study_ids

    await engine.dispose()
