import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.api.jobs import job_runtime, shutdown_jobs
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import (
    Base,
    Studies,
    StudyReports,
    Personas,
    EvidenceSources,
    EvidenceClaims,
)
from bebshax.jobs.orm import DurableJobs
from bebshax.jobs.store import SQLJobStore
from bebshax.main import create_app


@pytest.fixture
async def workflow_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workflow.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        application.state.db_engine = engine
        application.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        application.state.llm_service = None
        job_runtime(application)
        yield application
    finally:
        try:
            await shutdown_jobs(application)
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_workflow_fixture_uses_a_private_app(workflow_app: FastAPI) -> None:
    from bebshax.main import app as shared_app

    assert workflow_app is not shared_app
    runtime = workflow_app.state.job_runtime
    assert isinstance(runtime.store, SQLJobStore)
    assert runtime.store is workflow_app.state.job_store
    assert runtime.store.sessionmaker is workflow_app.state.db_sessionmaker
    async with runtime.store.sessionmaker() as session:
        assert session.bind is workflow_app.state.db_engine


@pytest.mark.asyncio
async def test_study_report_generation_and_versioning(workflow_app: FastAPI) -> None:
    """Verify report generation, multi-versioning, and latest report retrieval."""
    app = workflow_app
    session_maker = app.state.db_sessionmaker

    # Seed study with personas and evidence
    async with session_maker() as session:
        user = Users(id="usr_owner", email="owner@bebshax.com", full_name="Owner", hashed_password="pw", is_verified=True)
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
            owner_id="usr_owner",
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
        # 0. No LLM wired -> explicit 503, no template report row is written (R2).
        app.state.llm_service = None
        res_none = await client.post(
            "/api/studies/std_workflow_01/reports/generate",
            headers=headers,
            json={"title": "Should not exist"},
        )
        assert res_none.status_code == 503
        assert res_none.json()["error_code"] == "llm_unavailable"
        assert (await client.get("/api/studies/std_workflow_01/reports", headers=headers)).json() == []
        async with session_maker() as session:
            failed_job_id = await session.scalar(select(DurableJobs.id).where(
                DurableJobs.kind == "report_generation",
                DurableJobs.scope_id == "std_workflow_01",
                DurableJobs.owner_id == "usr_owner",
            ))
        assert failed_job_id is not None
        failed_job = await client.get(
            f"/api/studies/std_workflow_01/reports/generate/jobs/{failed_job_id}", headers=headers,
        )
        assert failed_job.status_code == 200, failed_job.text
        assert failed_job.json()["state"] == "failed"

        # Model-written report: the FakeAdapter stands in for the provider.
        import json as _json

        from bebshax.llm.adapters.base import RouteCandidate
        from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
        from bebshax.llm.router import PoolRouter

        report_json = _json.dumps(
            {
                "executive_summary": "Students in Dhaka are price-bound; the single stored claim supports a low tier.",
                "key_findings": ["74% of students spend under 3,000 BDT/month on lunch (src_01)."],
                "metrics": {"confidence_score": 0.3, "demand_score": 40},
            }
        )
        latest_claim = "Latest stored evidence: students prefer weekly payments of 50 BDT."
        updated_report_json = _json.dumps({
            "executive_summary": "The updated stored evidence favors weekly payments of 50 BDT.",
            "key_findings": [latest_claim],
            "metrics": {"confidence_score": 0.4, "demand_score": 55},
        })
        fake = FakeAdapter(
            routes=[FakeRoute(
                candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"),
                replies=[report_json, updated_report_json],
            )]
        )
        app.state.llm_service = PoolRouter({"freellmpool": fake, "openrouter": FakeAdapter([])})

        # 1. Generate version 1 report
        res_v1 = await client.post(
            "/api/studies/std_workflow_01/reports/generate",
            headers=headers,
            json={"title": "AI Meal Planner Decision Report V1"},
        )
        assert res_v1.status_code == 201, res_v1.text
        v1_data = res_v1.json()
        assert v1_data["version"] == 1
        assert v1_data["study_id"] == "std_workflow_01"
        assert v1_data["title"] == "AI Meal Planner Decision Report V1"
        assert len(v1_data["executive_summary"]) > 0
        assert len(v1_data["key_findings"]) > 0
        assert v1_data["metrics"]["synthesis_source"] == "llm"
        assert v1_data["metrics"]["served_by"] == "pollinations/deepseek-r1"
        assert v1_data["metrics"]["total_claims"] == 1 and v1_data["metrics"]["demand_score"] == 40
        report_1_id = v1_data["id"]
        assert len(fake.requests) == 1
        assert latest_claim not in " ".join(message.content for message in fake.requests[0].messages)

        # 2. Generate version 2 report
        async with session_maker() as session:
            stored_claim = await session.get(EvidenceClaims, "clm_01")
            assert stored_claim is not None
            stored_claim.claim_text = latest_claim
            await session.commit()
        res_v2 = await client.post(
            "/api/studies/std_workflow_01/reports/generate",
            headers=headers,
            json={"title": "AI Meal Planner Decision Report V2"},
        )
        assert res_v2.status_code == 201, res_v2.text
        v2_data = res_v2.json()
        assert v2_data["version"] == 2
        assert v2_data["key_findings"] == [latest_claim]
        assert v2_data["metrics"]["demand_score"] == 55
        report_2_id = v2_data["id"]
        assert report_2_id != report_1_id
        assert len(fake.requests) == 2
        assert latest_claim in " ".join(message.content for message in fake.requests[-1].messages)
        for generated_report in (v1_data, v2_data):
            job = await client.get(
                f"/api/studies/std_workflow_01/reports/generate/jobs/{generated_report['job_id']}",
                headers=headers,
            )
            assert job.status_code == 200, job.text
            assert job.json()["state"] == "completed"
            assert job.json()["result_refs"]["report_id"] == generated_report["id"]

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
        assert latest_data["key_findings"] == [latest_claim]
        assert latest_data["executive_summary"] == v2_data["executive_summary"]

        # 5. Get specific report by ID
        res_by_id = await client.get(f"/api/studies/std_workflow_01/reports/{report_1_id}", headers=headers)
        assert res_by_id.status_code == 200
        assert res_by_id.json()["version"] == 1
        assert res_by_id.json()["key_findings"] == v1_data["key_findings"]
        assert res_by_id.json()["executive_summary"] == v1_data["executive_summary"]


@pytest.mark.asyncio
async def test_study_reports_idor_security(workflow_app: FastAPI) -> None:
    """Verify IDOR prevention: User B cannot access or generate reports for User A's study."""
    app = workflow_app
    session_maker = app.state.db_sessionmaker

    async with session_maker() as session:
        user_a = Users(id="usr_a", email="user_a@bebshax.com", full_name="User A", hashed_password="pw", is_verified=True)
        user_b = Users(id="usr_b", email="user_b@bebshax.com", full_name="User B", hashed_password="pw", is_verified=True)
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
        assert res_list.status_code == 403

        # User B attempts to view User A's latest report
        res_latest = await client.get("/api/studies/std_a/reports/latest", headers=headers_b)
        assert res_latest.status_code == 403

        # User B attempts to view User A's specific report by ID
        res_single = await client.get("/api/studies/std_a/reports/rep_a", headers=headers_b)
        assert res_single.status_code == 403

        # User B attempts to generate report for User A's study
        res_gen = await client.post(
            "/api/studies/std_a/reports/generate",
            headers=headers_b,
            json={"title": "Malicious Report"},
        )
        assert res_gen.status_code == 404
        res_async_gen = await client.post("/api/studies/std_a/reports/generate/jobs", headers=headers_b)
        assert res_async_gen.status_code == 404
        anonymous_list = await client.get("/api/studies/std_a/reports")
        assert anonymous_list.status_code == 403
        anonymous_gen = await client.post("/api/studies/std_a/reports/generate")
        assert anonymous_gen.status_code == 404
        async with session_maker() as session:
            assert list(await session.scalars(select(DurableJobs))) == []
            reports = list(await session.scalars(select(StudyReports)))
            assert [report.id for report in reports] == ["rep_a"]


@pytest.mark.asyncio
async def test_dynamic_script_and_batch_interviews(workflow_app: FastAPI) -> None:
    """Verify dynamic script question generation and batch interview execution.

    Batch interviews must run through the REAL engine (post-audit fix): a
    FakeAdapter-backed router is wired, and the test asserts genuine turns —
    the fabricated-transcript fallback no longer exists.
    """
    from bebshax.interview.engine import InterviewEngine
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    app = workflow_app
    session_maker = app.state.db_sessionmaker
    fake = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="scripted"),
                # 1st call = script generation (must be model-written JSON — there is
                # no template fallback any more); later calls = interview turns.
                replies=[
                    '{"questions": ["How do you track gadget prices today?", "What made you miss a deal last time?", '
                    '"Would 100 taka a month feel fair for instant alerts?", "What would make you cancel?"]}'
                ],
                reply="I compare prices manually across three shops every week.",
            )
        ]
    )
    llm_router = PoolRouter({"openrouter": fake, "freellmpool": fake})
    app.state.llm_router = llm_router
    app.state.llm_service = llm_router
    app.state.interview_engine = InterviewEngine(llm_router, session_maker)

    async with session_maker() as session:
        user = Users(id="usr_user", email="user@bebshax.com", full_name="User", hashed_password="pw", is_verified=True)
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
            owner_id="usr_user",
            name="Samiul Alam",
            archetype="Smart Bargain Hunter",
            bio="Online electronics shopper",
            grounding_score=0.96,
        )
        session.add(p1)
        await session.commit()

    token = create_access_token({"sub": "usr_user", "email": "user@bebshax.com"})
    headers = {"Authorization": f"Bearer {token}"}

    try:
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

            # 2a. No script and no questions -> explicit 400, no canned questionnaire runs.
            async with session_maker() as s:
                std = await s.get(Studies, "std_script_01")
                saved_script = list(std.script_questions or [])
                std.script_questions = []
                await s.commit()
            res_noscript = await client.post(
                "/api/studies/std_script_01/interviews/batch-run",
                headers=headers,
                json={"persona_ids": ["per_samiul"]},
            )
            assert res_noscript.status_code == 400
            assert res_noscript.json()["error_code"] == "script_required"
            async with session_maker() as s:
                std = await s.get(Studies, "std_script_01")
                std.script_questions = saved_script
                await s.commit()

            # 2. Start batch synthetic interviews (async job).
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
            assert res_batch.status_code == 202
            start_data = res_batch.json()
            job_id = start_data["job_id"]
            assert start_data["status"] == "running"
            assert start_data["total_personas"] == 1
            assert start_data["personas"]["per_samiul"]["status"] in ("pending", "in_progress")

            await asyncio.wait_for(app.state.job_runtime.drain(), timeout=10)
            res_status = await client.get(
                f"/api/studies/std_script_01/interviews/batch-run/{job_id}",
                headers=headers,
            )
            assert res_status.status_code == 200, res_status.text
            job = res_status.json()
            assert job["state"] == "completed"
            assert job["status"] == "completed"
            assert job["completed_count"] == 1
            assert job["failed_count"] == 0
            entry = job["personas"]["per_samiul"]
            assert entry["status"] == "completed"
            interview_id = entry["interview_id"]

            # Unknown job ids are an honest 404 (e.g. lost in a restart).
            res_missing = await client.get(
                "/api/studies/std_script_01/interviews/batch-run/bjob_nope",
                headers=headers,
            )
            assert res_missing.status_code == 404

            # 3. The interview itself was persisted with REAL engine turns —
            # the fabricated-transcript fallback no longer exists.
            res_iv = await client.get(
                f"/api/studies/std_script_01/interviews/{interview_id}",
                headers=headers,
            )
            assert res_iv.status_code == 200
            interview = res_iv.json()
            assert interview["persona_id"] == "per_samiul"
            assert interview["turn_count"] >= 4  # 2 questions × (interviewer + persona)
            persona_turns = [t for t in interview["turns"] if t["role"] == "persona"]
            assert persona_turns and all(
                "I compare prices manually" in t["content"] for t in persona_turns
            )
            assert all(t.get("served_by") == "fake/scripted" for t in persona_turns)
    finally:
        await shutdown_jobs(app)
