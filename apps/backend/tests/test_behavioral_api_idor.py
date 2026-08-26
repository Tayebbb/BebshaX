"""Tests for Behavioral Testing REST API: study-scoping, CRUD, batch execution, comparison, and IDOR isolation."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.behavioral.engine import BehavioralSimulationEngine
from bebshax.behavioral.orm import (
    BehavioralInsights,
    BehavioralTestResults,
    BehavioralTestRuns,
    BehavioralTestScenarios,
    BehavioralTests,
)
from bebshax.config import get_settings
from bebshax.db.models import Base, Personas, Studies
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.main import create_app


@pytest.mark.asyncio
async def test_behavioral_api_crud_and_runs(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'behavioral_api.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        # Create user & study
        user = Users(id="usr_owner", email="owner@test.com", full_name="Owner User", hashed_password="hash", is_active=True, is_verified=True)
        study = Studies(id="std_owner", user_id="usr_owner", title="Owner Study", prompt="Testing behavioral")
        persona = Personas(id="p_owner_1", study_id="std_owner", owner_id="usr_owner", name="Persona 1")
        session.add_all([user, study, persona])
        await session.commit()

    app = create_app()
    app.state.db_sessionmaker = maker
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=['{"decision": "positive", "probability": 0.75, "confidence": "high", "key_factors": [], "motivators": [], "objections": [], "reasoning_summary": "Good"}'])])
    llm = SingleAdapterLLMService(adapter)
    app.state.behavioral_engine = BehavioralSimulationEngine(llm, maker)

    token = create_access_token({"sub": "usr_owner", "email": "owner@test.com"})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Behavioral Test
        create_resp = await client.post(
            "/api/studies/std_owner/behavioral-tests",
            json={
                "name": "Pricing Sensitivity Test",
                "description": "Test student willingness to pay ৳299/mo",
                "test_type": "pricing_test",
                "configuration": {"price": "৳299", "billing_period": "monthly"},
                "scenario_title": "Monthly Subscription",
                "scenario_text": "Unlimited access to automated meal planner",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        test_data = create_resp.json()
        assert test_data["name"] == "Pricing Sensitivity Test"
        test_id = test_data["id"]

        # 2. List Behavioral Tests
        list_resp = await client.get("/api/studies/std_owner/behavioral-tests", headers=headers)
        assert list_resp.status_code == 200
        tests = list_resp.json()
        assert len(tests) == 1
        assert tests[0]["id"] == test_id

        # 3. Get Metrics
        metrics_resp = await client.get("/api/studies/std_owner/behavioral-tests/metrics", headers=headers)
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert metrics["total_tests"] == 1

        # 4. Trigger Simulation Run
        run_resp = await client.post(
            f"/api/studies/std_owner/behavioral-tests/{test_id}/runs",
            json={
                "scenario_title": "Monthly Subscription",
                "scenario_text": "Unlimited access",
                "parameters": {"price": "৳299"},
                "target_population_type": "all",
            },
            headers=headers,
        )
        assert run_resp.status_code == 201
        run_data = run_resp.json()
        run_id = run_data["id"]

        # 5. List Runs
        runs_list_resp = await client.get(f"/api/studies/std_owner/behavioral-tests/{test_id}/runs", headers=headers)
        assert runs_list_resp.status_code == 200
        assert len(runs_list_resp.json()) == 1

        # 6. Get Run Detail & Results
        run_detail_resp = await client.get(f"/api/studies/std_owner/behavioral-tests/runs/{run_id}", headers=headers)
        assert run_detail_resp.status_code == 200
        assert run_detail_resp.json()["id"] == run_id


@pytest.mark.asyncio
async def test_behavioral_api_idor_isolation(tmp_path, monkeypatch):
    """Ensure User A cannot access or manipulate User B's behavioral tests."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'behavioral_idor.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        user_a = Users(id="usr_a", email="a@test.com", full_name="User A", hashed_password="hash", is_active=True, is_verified=True)
        user_b = Users(id="usr_b", email="b@test.com", full_name="User B", hashed_password="hash", is_active=True, is_verified=True)

        study_b = Studies(id="std_b", user_id="usr_b", title="Study B", prompt="B's idea")
        test_b = BehavioralTests(id="bt_b_1", study_id="std_b", user_id="usr_b", name="B's Secret Test", test_type="pricing_test")
        run_b = BehavioralTestRuns(id="btr_b_1", behavioral_test_id="bt_b_1", study_id="std_b", user_id="usr_b", status="completed")
        session.add_all([user_a, user_b, study_b, test_b, run_b])
        await session.commit()

    app = create_app()
    app.state.db_sessionmaker = maker

    token_a = create_access_token({"sub": "usr_a", "email": "a@test.com"})
    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # User A tries to list User B's tests
        resp1 = await client.get("/api/studies/std_b/behavioral-tests", headers=headers_a)
        assert resp1.status_code in (403, 404)

        # User A tries to view User B's test detail
        resp2 = await client.get("/api/studies/std_b/behavioral-tests/bt_b_1", headers=headers_a)
        assert resp2.status_code in (403, 404)

        # User A tries to run simulation on User B's test
        resp3 = await client.post(
            "/api/studies/std_b/behavioral-tests/bt_b_1/runs",
            json={"target_population_type": "all"},
            headers=headers_a,
        )
        assert resp3.status_code in (403, 404)

        # User A tries to view User B's run results
        resp4 = await client.get("/api/studies/std_b/behavioral-tests/runs/btr_b_1", headers=headers_a)
        assert resp4.status_code in (403, 404)

        # User A tries to delete User B's test
        resp5 = await client.delete("/api/studies/std_b/behavioral-tests/bt_b_1", headers=headers_a)
        assert resp5.status_code in (403, 404)
