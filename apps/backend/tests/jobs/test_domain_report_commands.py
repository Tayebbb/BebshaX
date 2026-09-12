from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from bebshax.api import studies
from bebshax.api.deps import get_session
from bebshax.api.errors import APIError
from bebshax.api.jobs import cancel_job_async, shutdown_jobs
from bebshax.auth.models import Users
from bebshax.db.models import Base, EvidenceClaims, Studies, StudyReports
from bebshax.jobs.orm import DurableJobs, JobCheckpoints
from bebshax.jobs.store import SQLJobStore
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute


@pytest.fixture
async def report_jobs_http(job_store, journal_engine, monkeypatch) -> AsyncIterator[SimpleNamespace]:
    async with journal_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = job_store.sessionmaker
    owner = Users(id="report-owner", email="reports@example.test", full_name="Synthetic Report Owner")
    async with maker() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add(Studies(id="report-study", user_id=owner.id, title="Synthetic report study", prompt="Synthetic idea"))
        session.add(EvidenceClaims(
            id="report-claim", study_id="report-study", user_id=owner.id,
            claim_text="Synthetic participants may need clearer scheduling.", status="inference",
        ))

    async def session_dependency():
        async with maker() as session:
            yield session

    app = FastAPI()
    app.include_router(studies.router, prefix="/api")
    app.state.db_sessionmaker = maker
    app.state.job_store = job_store
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[studies.get_current_user] = lambda: owner
    app.dependency_overrides[studies.get_optional_current_user] = lambda: owner
    monkeypatch.setattr(studies.limiter, "enabled", False)

    async def api_error(request, error):
        return JSONResponse(status_code=error.status_code, content={
            "detail": error.detail, "error_code": error.error_code, **error.extra,
        })

    app.add_exception_handler(APIError, api_error)
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="synthetic-report", context_window=100_000),
        reply=json.dumps({"executive_summary": "The supplied scheduling claim remains a synthetic inference."}),
    )])
    llm = SingleAdapterLLMService(adapter)
    complete = llm.complete
    started = asyncio.Event()
    release = asyncio.Event()

    async def held_complete(request):
        started.set()
        await release.wait()
        return await complete(request)

    monkeypatch.setattr(llm, "complete", held_complete)
    app.state.llm_service = llm
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(
                app=app, client=client, maker=maker, store=job_store,
                started=started, release=release, adapter=adapter,
            )
    finally:
        release.set()
        await shutdown_jobs(app)


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_report_routes_fence_and_checkpoint_every_publication(report_jobs_http, background, cancelled):
    context = report_jobs_http
    suffix = "/jobs" if background else ""
    pending = asyncio.create_task(context.client.post(
        f"/api/studies/report-study/reports/generate{suffix}",
        json={"title": "Synthetic report"}, headers={"Idempotency-Key": "report-command"},
    ))
    remote = SimpleNamespace(state=SimpleNamespace(job_store=SQLJobStore(context.maker)))
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        async with context.maker() as session:
            jobs = list(await session.scalars(select(DurableJobs)))
            assert len(jobs) == 1, "Every report entrypoint must durably admit before synthesis"
            job_id = jobs[0].id
            assert jobs[0].input_data["study_revision"] == 1
            checkpoints = list(await session.scalars(select(JobCheckpoints)))
            assert len(checkpoints) == 1 and checkpoints[0].status == "started"
        if cancelled:
            saved = await cancel_job_async(
                remote, job_id, kind="report_generation", scope_id="report-study", user_id="report-owner",
            )
            assert saved["state"] == "cancelled"
        context.release.set()
        response = await pending
        await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
        async with context.maker() as session:
            job = await session.get(DurableJobs, job_id)
            reports = list(await session.scalars(select(StudyReports)))
            if cancelled:
                assert job.status == "cancelled"
                assert reports == []
                study = await session.get(Studies, "report-study")
                assert study.findings is None and study.revision == 1
                assert response.status_code == (202 if background else 409)
            else:
                assert response.status_code == (202 if background else 201), response.text
                assert job.status == "completed"
                assert len(reports) == 1
                report = reports[0]
                checkpoint = (await session.scalars(select(JobCheckpoints))).one()
                assert checkpoint.status == "completed"
                assert checkpoint.result_refs["report_id"] == report.id == job.result_refs["report_id"]
                assert checkpoint.result_refs["input_manifest"] == report.metrics["input_manifest"]
                assert report.version == 1
        calls = len(context.adapter.requests)
        polled = await context.client.get(f"/api/studies/report-study/reports/generate/jobs/{job_id}")
        assert polled.status_code == 200
        assert len(context.adapter.requests) == calls
    finally:
        context.release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await shutdown_jobs(remote)


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("changed_input", ["study", "claim"])
async def test_report_rejects_changed_queued_inputs_before_provider_work(
    report_jobs_http, monkeypatch, background, changed_input,
):
    context = report_jobs_http
    claim_job = context.store.claim

    async def change_before_claim(*args, **kwargs):
        async with context.maker() as session, session.begin():
            if changed_input == "study":
                study = await session.get(Studies, "report-study")
                study.prompt = "A newer synthetic idea"
            else:
                claim = await session.get(EvidenceClaims, "report-claim")
                claim.claim_text = "A newer synthetic claim"
        return await claim_job(*args, **kwargs)

    monkeypatch.setattr(context.store, "claim", change_before_claim)
    context.release.set()
    suffix = "/jobs" if background else ""
    response = await context.client.post(
        f"/api/studies/report-study/reports/generate{suffix}", headers={"Idempotency-Key": "stale-report"},
    )
    await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
    assert response.status_code == (202 if background else 409), response.text
    assert not context.started.is_set()
    assert not context.adapter.requests
    async with context.maker() as session:
        assert (await session.scalars(select(DurableJobs))).one().status == "failed"
        assert not list(await session.scalars(select(StudyReports)))
        assert not list(await session.scalars(select(JobCheckpoints)))


@pytest.mark.parametrize("newer_status", ["archived", "completed"])
async def test_report_retains_historical_artifact_without_overwriting_newer_study(report_jobs_http, newer_status):
    context = report_jobs_http
    response = await context.client.post("/api/studies/report-study/reports/generate/jobs")
    assert response.status_code == 202
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        async with context.maker() as session, session.begin():
            study = await session.get(Studies, "report-study")
            study.status = newer_status
            study.prompt = "A newer synthetic idea"
            study.findings = {"report_id": "newer-study-findings"}
        context.release.set()
        await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
    finally:
        context.release.set()
    async with context.maker() as session:
        report = (await session.scalars(select(StudyReports))).one()
        study = await session.get(Studies, "report-study")
        job = await session.get(DurableJobs, response.json()["job_id"])
        assert job.status == "completed", job.error
        assert study.status == newer_status
        assert study.findings == {"report_id": "newer-study-findings"}
        assert study.revision == 2
        assert report.metrics["study_projection_applied"] is False
        assert report.metrics["input_manifest"]["study_revision"] == 1
        assert report.metrics["input_manifest"]["input_versions"] == job.input_data["input_versions"]


async def test_report_command_replays_its_original_snapshot_after_restart(report_jobs_http):
    context = report_jobs_http
    context.release.set()
    path = "/api/studies/report-study/reports/generate/jobs"
    headers = {"Idempotency-Key": "completed-report"}
    first = await context.client.post(path, json={"title": "Original report"}, headers=headers)
    assert first.status_code == 202
    await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
    await shutdown_jobs(context.app)
    del context.app.state.job_runtime
    request_count = len(context.adapter.requests)

    repeated = await context.client.post(path, json={"title": "Original report"}, headers=headers)
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["job_id"] == first.json()["job_id"]
    assert repeated.json()["status"] == "completed"
    assert len(context.adapter.requests) == request_count
    conflict = await context.client.post(path, json={"title": "Changed report"}, headers=headers)
    assert conflict.status_code == 409
    async with context.maker() as session:
        assert len(list(await session.scalars(select(DurableJobs)))) == 1
        assert len(list(await session.scalars(select(StudyReports)))) == 1


async def test_report_cancel_endpoint_persists_an_idempotent_terminal_outcome(report_jobs_http):
    context = report_jobs_http
    response = await context.client.post("/api/studies/report-study/reports/generate/jobs")
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        path = f"/api/studies/report-study/reports/generate/jobs/{job_id}/cancel"
        cancelled = await context.client.post(path)
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        repeated = await context.client.post(path)
        assert repeated.status_code == 200 and repeated.json()["state"] == "cancelled"
        context.release.set()
        await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
        async with context.maker() as session:
            assert (await session.get(DurableJobs, job_id)).status == "cancelled"
            assert not list(await session.scalars(select(StudyReports)))
    finally:
        context.release.set()


async def test_report_pins_current_typed_versions_without_creating_lineage(report_jobs_http):
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import DatasetSources, Personas
    from bebshax.personas.orm import PersonaVersions

    context = report_jobs_http
    async with context.maker() as session, session.begin():
        session.add(DatasetSources(
            id="report-dataset", study_id="report-study", user_id="report-owner", name="Synthetic source",
            file_path="synthetic-current.json", content_hash="a" * 64,
        ))
        session.add(Personas(
            id="report-persona", study_id="report-study", user_id="report-owner", owner_id="report-owner",
            name="Synthetic Participant", version=1,
        ))
        await session.flush()
        session.add(PersonaVersions(
            persona_id="report-persona", owner_id="report-owner", study_id="report-study", version=1,
            capture_kind="generated", snapshot={"id": "report-persona", "owner_id": "report-owner", "version": 1},
        ))
        session.add_all([
            DatasetVersions(
                id=version_id, dataset_id="report-dataset", owner_id="report-owner", version=number,
                content_hash=content_hash, records_hash="c" * 64, file_path=file_path,
                row_count=1, column_count=1, schema_metadata={}, statistics={}, segments=[],
            )
            for version_id, number, content_hash, file_path in (
                ("report-current-version", 1, "a" * 64, "synthetic-current.json"),
                ("report-other-version", 2, "b" * 64, "synthetic-other.json"),
            )
        ])
    context.release.set()
    response = await context.client.post("/api/studies/report-study/reports/generate/jobs")
    assert response.status_code == 202
    await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
    async with context.maker() as session:
        job = await session.get(DurableJobs, response.json()["job_id"])
        assert job.status == "completed", job.error
        versions = job.input_data["input_versions"]
        assert versions["datasets"][0]["version_id"] == "report-current-version"
        assert versions["datasets"][0]["version"] == 1
        assert versions["personas"][0]["version"] == 1
        assert versions["personas"][0]["capture_kind"] == "generated"
        assert len(versions["personas"][0]["snapshot_hash"]) == 64
        report = (await session.scalars(select(StudyReports))).one()
        assert report.metrics["input_manifest"]["input_versions"] == versions
        assert len(list(await session.scalars(select(DatasetVersions)))) == 2
        assert len(list(await session.scalars(select(PersonaVersions)))) == 1