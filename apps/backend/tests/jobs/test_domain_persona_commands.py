from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from bebshax.api import personas as persona_api
from bebshax.api.deps import get_session
from bebshax.api.errors import APIError
from bebshax.api.jobs import cancel_job_async, shutdown_jobs
from bebshax.auth.models import Users
from bebshax.db.models import Base, MarketSegments, PersonaGenerationRuns, Personas, Studies
from bebshax.jobs.orm import DurableJobs, JobCheckpoints
from bebshax.jobs.store import SQLJobStore
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.personas import service as persona_module
from bebshax.personas.generator import GeneratedPersonaDraft
from bebshax.personas.orm import PersonaVersions


@pytest.fixture
async def persona_jobs_http(job_store, journal_engine, monkeypatch):
    import bebshax.datasets.orm

    async with journal_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = job_store.sessionmaker
    owner = Users(id="persona-owner", email="personas@example.test", full_name="Synthetic Owner")
    async with maker() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add(Studies(id="persona-study", user_id=owner.id, title="Synthetic persona study"))
        session.add(MarketSegments(
            id="persona-segment", study_id="persona-study", user_id=owner.id,
            segmentation_run_id="persona-segmentation", name="Synthetic segment", population_count=1,
            description="A synthetic test segment",
        ))
    app = FastAPI()
    app.include_router(persona_api.router, prefix="/api")
    app.state.db_sessionmaker = maker
    app.state.job_store = job_store
    app.state.llm_service = SingleAdapterLLMService(FakeAdapter([]))

    async def session_dependency():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[persona_api.get_current_user] = lambda: owner
    app.dependency_overrides[persona_api.get_optional_current_user] = lambda: owner
    monkeypatch.setattr(persona_api.limiter, "enabled", False)
    monkeypatch.setattr(persona_api, "get_persona_ml", lambda app: None)

    async def api_error(request, error):
        return JSONResponse(status_code=error.status_code, content={
            "detail": error.detail, "error_code": error.error_code, **error.extra,
        })

    app.add_exception_handler(APIError, api_error)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        started.set()
        await release.wait()
        return [GeneratedPersonaDraft(name="Synthetic participant", segment_id="persona-segment")]

    monkeypatch.setattr(persona_module, "generate_personas_for_study", generate)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(app=app, client=client, maker=maker, store=job_store, started=started, release=release, calls=calls)
    finally:
        release.set()
        await shutdown_jobs(app)


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_persona_commands_fence_cohort_and_version_publication(persona_jobs_http, background, cancelled):
    context = persona_jobs_http
    suffix = "/jobs" if background else ""
    pending = asyncio.create_task(context.client.post(
        f"/api/studies/persona-study/personas/generate{suffix}", json={"target_count": 1},
        headers={"Idempotency-Key": "persona-command"},
    ))
    remote = SimpleNamespace(state=SimpleNamespace(job_store=SQLJobStore(context.maker)))
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        async with context.maker() as session:
            jobs = list(await session.scalars(select(DurableJobs)))
            assert len(jobs) == 1
            job_id = jobs[0].id
            assert jobs[0].result_refs["run_id"]
            checkpoint = (await session.scalars(select(JobCheckpoints))).one()
            assert checkpoint.status == "started"
        if cancelled:
            await cancel_job_async(remote, job_id, kind="persona_generation", scope_id="persona-study", user_id="persona-owner")
        context.release.set()
        response = await pending
        await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
        polled = await context.client.get(f"/api/studies/persona-study/personas/generate/jobs/{job_id}")
        assert polled.status_code == 200
        async with context.maker() as session:
            run = (await session.scalars(select(PersonaGenerationRuns))).one()
            job = await session.get(DurableJobs, job_id)
            assert job.status == run.status == ("cancelled" if cancelled else "completed")
            assert len(list(await session.scalars(select(Personas)))) == (0 if cancelled else 1)
            assert len(list(await session.scalars(select(PersonaVersions)))) == (0 if cancelled else 1)
            if not cancelled:
                assert response.status_code == (202 if background else 201)
                assert (await session.get(Studies, "persona-study")).persona_count == 1
                assert (await session.scalars(select(JobCheckpoints))).one().status == "completed"
    finally:
        context.release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await shutdown_jobs(remote)


@pytest.mark.parametrize("background", [False, True])
async def test_persona_command_rejects_changed_queued_study_before_selection(persona_jobs_http, monkeypatch, background):
    context = persona_jobs_http
    claim = context.store.claim

    async def change_before_claim(*args, **kwargs):
        async with context.maker() as session, session.begin():
            study = await session.get(Studies, "persona-study")
            study.prompt = "Changed synthetic idea"
        return await claim(*args, **kwargs)

    monkeypatch.setattr(context.store, "claim", change_before_claim)
    context.release.set()
    suffix = "/jobs" if background else ""
    response = await context.client.post(f"/api/studies/persona-study/personas/generate{suffix}", json={"target_count": 1})
    if getattr(context.app.state, "job_runtime", None) is not None:
        await context.app.state.job_runtime.drain()
    assert response.status_code == (202 if background else 409), response.text
    assert context.calls == []
    async with context.maker() as session:
        assert not list(await session.scalars(select(Personas)))


async def test_persona_cancel_route_preserves_terminal_run_projection(persona_jobs_http):
    context = persona_jobs_http
    response = await context.client.post("/api/studies/persona-study/personas/generate/jobs", json={"target_count": 1})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        cancelled = await context.client.post(f"/api/studies/persona-study/personas/generate/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "cancelled"
        context.release.set()
        await context.app.state.job_runtime.drain()
        async with context.maker() as session:
            assert (await session.scalars(select(PersonaGenerationRuns))).one().status == "cancelled"
            assert not list(await session.scalars(select(Personas)))
    finally:
        context.release.set()


async def test_persona_completed_command_replays_without_selecting_a_new_source(persona_jobs_http):
    context = persona_jobs_http
    context.release.set()
    path = "/api/studies/persona-study/personas/generate"
    headers = {"Idempotency-Key": "same-persona-command"}
    first = await context.client.post(path, json={"target_count": 1}, headers=headers)
    assert first.status_code == 201, first.text
    await shutdown_jobs(context.app)
    del context.app.state.job_runtime
    repeated = await context.client.post(path, json={"target_count": 1}, headers=headers)
    assert repeated.status_code == 201 and repeated.json() == first.json()
    assert len(context.calls) == 1


@pytest.mark.parametrize("changed_input", ["study", "segment", "dataset"])
async def test_persona_inflight_input_change_rolls_back_the_entire_cohort(persona_jobs_http, changed_input):
    from bebshax.db.models import DatasetSources

    context = persona_jobs_http
    response = await context.client.post("/api/studies/persona-study/personas/generate/jobs", json={"target_count": 1})
    assert response.status_code == 202
    try:
        await asyncio.wait_for(context.started.wait(), 5)
        async with context.maker() as session, session.begin():
            if changed_input == "study":
                study = await session.get(Studies, "persona-study")
                study.prompt = "Changed during selection"
            elif changed_input == "segment":
                segment = await session.get(MarketSegments, "persona-segment")
                segment.description = "Changed segment during selection"
            else:
                session.add(DatasetSources(
                    id="new-selection-input", study_id="persona-study", user_id="persona-owner",
                    name="New synthetic input during selection",
                ))
        context.release.set()
        await asyncio.wait_for(context.app.state.job_runtime.drain(), 10)
        async with context.maker() as session:
            job = await session.get(DurableJobs, response.json()["job_id"])
            run = (await session.scalars(select(PersonaGenerationRuns))).one()
            assert job.status == run.status == "failed"
            assert job.error_code == "persona_input_changed"
            assert not list(await session.scalars(select(Personas)))
            assert not list(await session.scalars(select(PersonaVersions)))
            assert (await session.get(Studies, "persona-study")).persona_count == 0
    finally:
        context.release.set()