"""Integration and unit tests for Autonomous Evidence and Dataset Discovery."""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, DatasetCandidates, DatasetSources, ResearchPlans, Studies
from bebshax.main import app
from bebshax.research.service import ResearchEngineService


@pytest.mark.asyncio
async def test_full_autonomous_research_service_execution():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    study_id = "std_auto_test_1"
    user_id = "usr_auto_test_1"

    async with session_maker() as session:
        user = Users(id=user_id, email="auto_test@example.com", full_name="Auto Tester", hashed_password="pw")
        study = Studies(
            id=study_id,
            user_id=user_id,
            title="AI Meal Planner for University Students",
            type="interviews",
            goal="demand_validation",
            prompt="I want to build an AI-powered meal planning app for university students in Bangladesh with monthly budget under 5000 BDT.",
            status="draft",
        )
        session.add_all([user, study])
        await session.commit()

        service = ResearchEngineService()
        run = await service.run_study_research(session, study, user_id=user_id)

        assert run.status == "completed"
        assert run.current_step == "completed"
        assert run.query_count > 0
        assert run.source_count > 0
        assert run.claim_count > 0
        assert run.dataset_candidate_count > 0
        assert run.dataset_imported_count > 0

        # Verify Research Plan was stored
        plan = await service.get_research_plan(session, study_id)
        assert plan is not None
        assert len(plan["target_market"]) > 0
        assert len(plan["dataset_requirements"]) > 0

        # Verify Dataset Candidates were stored
        candidates = await service.list_dataset_candidates(session, study_id)
        assert len(candidates) > 0
        imported = [c for c in candidates if c["selection_status"] == "imported"]
        assert len(imported) > 0
        assert imported[0]["imported_dataset_id"] is not None


@pytest.mark.asyncio
async def test_research_endpoints_and_idor_protection():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    owner_id = "usr_owner_123"
    other_user_id = "usr_intruder_456"
    study_id = "std_idor_research_1"

    async with session_maker() as session:
        user_owner = Users(id=owner_id, email="owner@example.com", full_name="Owner", hashed_password="pw")
        user_other = Users(id=other_user_id, email="intruder@example.com", full_name="Other", hashed_password="pw")
        study = Studies(
            id=study_id,
            user_id=owner_id,
            title="Student Study Habits in Bangladesh",
            type="interviews",
            prompt="Online learning habits and exam preparation tools in Bangladesh",
            status="ready",
        )
        session.add_all([user_owner, user_other, study])
        await session.commit()

        service = ResearchEngineService()
        await service.run_study_research(session, study, user_id=owner_id)

    token_owner = create_access_token({"sub": owner_id, "email": "owner@example.com"})
    token_other = create_access_token({"sub": other_user_id, "email": "intruder@example.com"})
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    headers_other = {"Authorization": f"Bearer {token_other}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Intruder receives 404
        res_plan_other = await ac.get(f"/api/studies/{study_id}/research/plan", headers=headers_other)
        assert res_plan_other.status_code == 404

        res_cands_other = await ac.get(f"/api/studies/{study_id}/datasets/candidates", headers=headers_other)
        assert res_cands_other.status_code == 404

        # 2. Owner access succeeds
        res_plan_owner = await ac.get(f"/api/studies/{study_id}/research/plan", headers=headers_owner)
        assert res_plan_owner.status_code == 200
        plan_data = res_plan_owner.json()
        assert "target_market" in plan_data
        assert "dataset_requirements" in plan_data

        res_cands_owner = await ac.get(f"/api/studies/{study_id}/datasets/candidates", headers=headers_owner)
        assert res_cands_owner.status_code == 200
        cands_data = res_cands_owner.json()
        assert len(cands_data) > 0
        assert "relevance_score" in cands_data[0]
        assert "selection_reason" in cands_data[0]
