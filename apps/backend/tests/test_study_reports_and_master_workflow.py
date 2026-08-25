import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.engine import init_database
from bebshax.db.models import (
    Base,
    Studies,
    StudyReports,
    Personas,
    EvidenceSources,
    EvidenceClaims,
)
from bebshax.interview.orm import (
    Conversations,
    ConversationTurns,
    Interviews,
    InterviewTurns,
)
from bebshax.main import app


@pytest.mark.asyncio
async def test_study_report_generation_and_versioning():
    """Verify report generation, multi-versioning, and latest report retrieval."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    # Seed study with personas and evidence
    async with session_maker() as session:
        user = Users(id="usr_owner", email="owner@bebshax.com", full_name="Owner", hashed_password="pw")
        session.add(user)

        study = Studies(
            id="std_workflow_01",
            user_id="usr_owner",
            title="AI Meal Planner Study",
            prompt="AI meal planner for university students in Dhaka with 200 taka/mo pricing",
            goal="demand_validation",
            target_audience="University students in Dhaka",
            pricing_hypothesis="200 BDT/month",
            status="in_progress",
            step=4,
        )
        session.add(study)

        p1 = Personas(
            id="per_01",
            study_id="std_workflow_01",
            user_id="usr_owner",
            name="Samiul Alam",
            archetype="Budget Student",
            bio="Student looking for affordable meal options",
            grounding_score=0.95,
        )
        session.add(p1)

        src = EvidenceSources(
            id="src_01",
            study_id="std_workflow_01",
            user_id="usr_owner",
            title="Dhaka University Student Budget Survey 2026",
            source_type="report",
            content="74% of university students spend less than 3,000 BDT per month on lunch.",
            content_hash="hash_survey_01",
            url="https://example.com/survey",
            relevance_score=0.92,
        )
        session.add(src)

        claim = EvidenceClaims(
            id="clm_01",
            study_id="std_workflow_01",
            user_id="usr_owner",
            claim_text="74% of university students spend less than 3,000 BDT per month on lunch",
            confidence=0.88,
        )
        session.add(claim)
        await session.commit()

    token = create_access_token({"sub": "usr_owner", "email": "owner@bebshax.com"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate version 1 report
        res_v1 = await client.post(
            "/api/studies/std_workflow_01/reports/generate",
            headers=headers,
            json={"title": "AI Meal Planner Decision Report V1"},
        )
        assert res_v1.status_code == 201
        v1_data = res_v1.json()
        assert v1_data["version"] == 1
        assert v1_data["study_id"] == "std_workflow_01"
        assert v1_data["title"] == "AI Meal Planner Decision Report V1"
        assert len(v1_data["executive_summary"]) > 0
        assert len(v1_data["key_findings"]) > 0
        report_1_id = v1_data["id"]

        # 2. Generate version 2 report
        res_v2 = await client.post(
            "/api/studies/std_workflow_01/reports/generate",
            headers=headers,
            json={"title": "AI Meal Planner Decision Report V2"},
        )
        assert res_v2.status_code == 201
        v2_data = res_v2.json()
        assert v2_data["version"] == 2
        report_2_id = v2_data["id"]

        # 3. List reports (should return both, newest first)
        res_list = await client.get("/api/studies/std_workflow_01/reports", headers=headers)
        assert res_list.status_code == 200
        reports = res_list.json()
        assert len(reports) == 2
        assert reports[0]["version"] == 2
        assert reports[1]["version"] == 1

        # 4. Get latest report
        res_latest = await client.get("/api/studies/std_workflow_01/reports/latest", headers=headers)
        assert res_latest.status_code == 200
        latest_data = res_latest.json()
        assert latest_data["id"] == report_2_id
        assert latest_data["version"] == 2

        # 5. Get specific report by ID
        res_by_id = await client.get(f"/api/studies/std_workflow_01/reports/{report_1_id}", headers=headers)
        assert res_by_id.status_code == 200
        assert res_by_id.json()["version"] == 1


@pytest.mark.asyncio
async def test_study_reports_idor_security():
    """Verify IDOR prevention: User B cannot access or generate reports for User A's study."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    async with session_maker() as session:
        user_a = Users(id="usr_a", email="user_a@bebshax.com", full_name="User A", hashed_password="pw")
        user_b = Users(id="usr_b", email="user_b@bebshax.com", full_name="User B", hashed_password="pw")
        session.add_all([user_a, user_b])

        study_a = Studies(
            id="std_a",
            user_id="usr_a",
            title="Private Study A",
            prompt="Secret project prompt",
            status="completed",
        )
        session.add(study_a)

        report_a = StudyReports(
            id="rep_a",
            study_id="std_a",
            user_id="usr_a",
            version=1,
            title="Private Report A",
            executive_summary="Secret findings",
            key_findings=["Finding 1"],
            recommendations=["Rec 1"],
        )
        session.add(report_a)
        await session.commit()

    token_b = create_access_token({"sub": "usr_b", "email": "user_b@bebshax.com"})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User B attempts to view User A's reports list
        res_list = await client.get("/api/studies/std_a/reports", headers=headers_b)
        assert res_list.status_code in (403, 404)

        # User B attempts to view User A's latest report
        res_latest = await client.get("/api/studies/std_a/reports/latest", headers=headers_b)
        assert res_latest.status_code in (403, 404)

        # User B attempts to view User A's specific report by ID
        res_single = await client.get("/api/studies/std_a/reports/rep_a", headers=headers_b)
        assert res_single.status_code in (403, 404)

        # User B attempts to generate report for User A's study
        res_gen = await client.post(
            "/api/studies/std_a/reports/generate",
            headers=headers_b,
            json={"title": "Malicious Report"},
        )
        assert res_gen.status_code in (403, 404)


@pytest.mark.asyncio
async def test_dynamic_script_and_batch_interviews():
    """Verify dynamic script question generation and batch interview execution."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    async with session_maker() as session:
        user = Users(id="usr_user", email="user@bebshax.com", full_name="User", hashed_password="pw")
        session.add(user)

        study = Studies(
            id="std_script_01",
            user_id="usr_user",
            title="E-commerce Price Tracker",
            prompt="Price drop alert website for gadgets in Bangladesh charging 100 taka per month",
            status="in_progress",
        )
        session.add(study)

        p1 = Personas(
            id="per_samiul",
            study_id="std_script_01",
            user_id="usr_user",
            name="Samiul Alam",
            archetype="Smart Bargain Hunter",
            bio="Online electronics shopper",
            grounding_score=0.96,
        )
        session.add(p1)
        await session.commit()

    token = create_access_token({"sub": "usr_user", "email": "user@bebshax.com"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Generate dynamic script questions
        res_script = await client.post(
            "/api/studies/std_script_01/script/generate",
            headers=headers,
            json={"prompt": "Price drop alert website for gadgets in Bangladesh", "question_count": 4},
        )
        assert res_script.status_code == 200
        script_data = res_script.json()
        assert len(script_data["questions"]) >= 3
        assert script_data["study_id"] == "std_script_01"

        # 2. Run batch synthetic interviews
        res_batch = await client.post(
            "/api/studies/std_script_01/interviews/batch-run",
            headers=headers,
            json={
                "persona_ids": ["per_samiul"],
                "questions": [
                    "How do you currently track product discounts across shops?",
                    "Would you pay 100 taka per month for instant SMS alerts?",
                ],
            },
        )
        assert res_batch.status_code in (200, 201)
        batch_data = res_batch.json()
        assert batch_data["completed_count"] == 1
        assert len(batch_data["interviews"]) == 1
        assert batch_data["interviews"][0]["persona_id"] == "per_samiul"
        assert batch_data["interviews"][0]["turn_count"] >= 2
