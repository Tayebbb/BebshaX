"""Async generation jobs (item 4): persona + report generation run as
background jobs — POST returns 202 + job_id immediately, the UI polls, and
failures surface honestly in job.error (never a hung request)."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, PersonaGenerationRuns, Personas, Studies, StudyReports


@pytest.fixture
async def jobs_app(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                Users(id="usr_owner", email="owner@example.com", hashed_password="x", full_name="Owner"),
                Studies(id="std_j", user_id="usr_owner", title="Job Study", status="in_progress"),
            ]
        )
        await session.commit()

    from bebshax.main import create_app

    app = create_app()
    app.state.db_sessionmaker = maker
    return app, maker


def _owner() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': 'usr_owner'})}"}


async def _poll_until_done(client, url, headers=None, attempts=100) -> dict:
    for _ in range(attempts):
        res = await client.get(url, headers=headers or {})
        assert res.status_code == 200
        job = res.json()
        if job["status"] != "running":
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("job never terminated")


@pytest.mark.asyncio
async def test_persona_generation_job_completes_with_sync_contract(jobs_app, monkeypatch):
    app, _ = jobs_app

    class FakeService:
        def __init__(self, session, llm_service=None, *, ml_generator=None):
            assert ml_generator is not None

        async def create_generation_run(self, *, study_id, user_id, **_):
            run = PersonaGenerationRuns(
                id="pgen_1", study_id=study_id, user_id=user_id, status="completed",
                target_count=2, generated_count=2, valid_count=2, warning_count=0,
            )
            personas = [
                Personas(id="per_j1", study_id=study_id, user_id=user_id,
                         owner_id=user_id, name="Jobbed One", version=1),
                Personas(id="per_j2", study_id=study_id, user_id=user_id,
                         owner_id=user_id, name="Jobbed Two", version=1),
            ]
            return run, personas

    from bebshax.api import personas as personas_api

    monkeypatch.setattr(personas_api, "PersonaGenerationService", FakeService)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/personas/generate/jobs",
            json={"personas_per_segment": 1},
            headers=_owner(),
        )
        assert res.status_code == 202
        job_id = res.json()["job_id"]

        job = await _poll_until_done(
            client, f"/api/studies/std_j/personas/generate/jobs/{job_id}", headers=_owner()
        )
        assert job["status"] == "completed"
        # result carries the exact sync-endpoint contract
        assert job["result"]["run"]["id"] == "pgen_1"
        assert [p["id"] for p in job["result"]["personas"]] == ["per_j1", "per_j2"]
        assert job["finished_at"] is not None


@pytest.mark.asyncio
async def test_persona_generation_job_surfaces_value_errors(jobs_app, monkeypatch):
    app, _ = jobs_app

    class ExplodingService:
        def __init__(self, session, llm_service=None, *, ml_generator=None):
            assert ml_generator is not None

        async def create_generation_run(self, **_):
            raise ValueError("Study has no market segments; run segmentation first.")

    from bebshax.api import personas as personas_api

    monkeypatch.setattr(personas_api, "PersonaGenerationService", ExplodingService)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/personas/generate/jobs", json={}, headers=_owner()
        )
        assert res.status_code == 202
        job = await _poll_until_done(
            client,
            f"/api/studies/std_j/personas/generate/jobs/{res.json()['job_id']}",
            headers=_owner(),
        )
        assert job["status"] == "failed"
        # ValueError = user-actionable — the message passes through
        assert "segmentation" in job["error"]


@pytest.mark.asyncio
async def test_persona_generation_job_requires_auth(jobs_app):
    app, _ = jobs_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/studies/std_j/personas/generate/jobs", json={})
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_unexpected_job_errors_are_redacted(jobs_app, monkeypatch):
    """Internal crashes must never leak details to the client (only logs)."""
    app, _ = jobs_app

    class CrashingService:
        def __init__(self, session, llm_service=None, *, ml_generator=None):
            assert ml_generator is not None

        async def create_generation_run(self, **_):
            raise RuntimeError("postgres://secret@host — internal state dump")

    from bebshax.api import personas as personas_api

    monkeypatch.setattr(personas_api, "PersonaGenerationService", CrashingService)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/personas/generate/jobs", json={}, headers=_owner()
        )
        job = await _poll_until_done(
            client,
            f"/api/studies/std_j/personas/generate/jobs/{res.json()['job_id']}",
            headers=_owner(),
        )
        assert job["status"] == "failed"
        assert job["error"] == "RuntimeError: persona_generation failed"
        assert "secret" not in job["error"]


@pytest.mark.asyncio
async def test_domain_failures_pass_their_message_through(jobs_app, monkeypatch):
    """R2/R6 honest failures (context window, no route) are user-meaningful."""
    from bebshax.llm import AllCandidatesFailed

    app, _ = jobs_app

    class NoRouteService:
        def __init__(self, session, llm_service=None, *, ml_generator=None):
            assert ml_generator is not None

        async def create_generation_run(self, **_):
            class _Prov:
                attempts: list = []

            raise AllCandidatesFailed(_Prov())

    from bebshax.api import personas as personas_api

    monkeypatch.setattr(personas_api, "PersonaGenerationService", NoRouteService)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/personas/generate/jobs", json={}, headers=_owner()
        )
        job = await _poll_until_done(
            client,
            f"/api/studies/std_j/personas/generate/jobs/{res.json()['job_id']}",
            headers=_owner(),
        )
        assert job["status"] == "failed"
        # AllCandidatesFailed's own message — passed through, not redacted
        assert "all candidates failed" in job["error"]


@pytest.mark.asyncio
async def test_report_generation_job_completes(jobs_app, monkeypatch):
    app, _ = jobs_app

    class FakeReportService:
        def __init__(self, session=None, llm_service=None):
            pass

        async def generate_report(self, *, study_id, user_id, custom_title=None):
            return StudyReports(
                id="rep_1", study_id=study_id, user_id=user_id, version=1,
                title=custom_title or "Findings", executive_summary="Summary.",
            )

    from bebshax.api import studies as studies_api

    monkeypatch.setattr(studies_api, "StudyReportService", FakeReportService)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/reports/generate/jobs",
            json={"title": "Q3 Validation"},
            headers=_owner(),
        )
        assert res.status_code == 202
        job = await _poll_until_done(
            client,
            f"/api/studies/std_j/reports/generate/jobs/{res.json()['job_id']}",
            headers=_owner(),
        )
        assert job["status"] == "completed"
        assert job["result"]["title"] == "Q3 Validation"
        assert job["result"]["id"] == "rep_1"


@pytest.mark.asyncio
async def test_job_ids_are_scoped_to_study_and_kind(jobs_app, monkeypatch):
    app, maker = jobs_app

    class FakeReportService:
        def __init__(self, session=None, llm_service=None):
            pass

        async def generate_report(self, *, study_id, user_id, custom_title=None):
            return StudyReports(id="rep_x", study_id=study_id, user_id=user_id,
                                version=1, title="T", executive_summary="S")

    from bebshax.api import studies as studies_api

    monkeypatch.setattr(studies_api, "StudyReportService", FakeReportService)

    async with maker() as session:
        session.add(Studies(id="std_other", user_id="usr_owner", title="Other", status="draft"))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/studies/std_j/reports/generate/jobs", json={}, headers=_owner()
        )
        job_id = res.json()["job_id"]
        # same job id through ANOTHER study's poll endpoint → 404
        cross = await client.get(
            f"/api/studies/std_other/reports/generate/jobs/{job_id}", headers=_owner()
        )
        assert cross.status_code == 404
        # and through the wrong-kind endpoint → 404
        wrong_kind = await client.get(
            f"/api/studies/std_j/personas/generate/jobs/{job_id}", headers=_owner()
        )
        assert wrong_kind.status_code == 404
        # unknown id → 404 with the restart hint
        missing = await client.get(
            "/api/studies/std_j/reports/generate/jobs/job_nope", headers=_owner()
        )
        assert missing.status_code == 404
        assert "restart" in missing.json()["detail"]


@pytest.mark.asyncio
async def test_report_job_is_owner_gated(jobs_app):
    app, _ = jobs_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # anonymous cannot start a job on an owned study — 404-first: the
        # study is unreadable to the caller, so its existence must not leak
        res = await client.post("/api/studies/std_j/reports/generate/jobs", json={})
        assert res.status_code == 404