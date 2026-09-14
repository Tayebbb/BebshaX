from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import create_autospec

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from bebshax.api import datasets as dataset_api, evidence, segmentation
from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.deps import get_session
from bebshax.api.errors import APIError
from bebshax.api.jobs import shutdown_jobs
from bebshax.auth.models import Users
from bebshax.db.models import Base, ResearchRuns, SegmentationRuns, Studies
from bebshax.jobs.orm import DurableJobs, JobCheckpoints


@pytest.fixture
async def feature_jobs_http(job_store, journal_engine, monkeypatch):
    async with journal_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = job_store.sessionmaker
    owner = Users(id="feature-owner", email="features@example.test", full_name="Synthetic Owner")
    async with maker() as session, session.begin():
        session.add(owner)
        await session.flush()
        session.add(Studies(id="feature-study", user_id=owner.id, title="Synthetic study", prompt="Synthetic idea"))

    async def session_dependency():
        async with maker() as session:
            yield session

    app = FastAPI()
    app.include_router(evidence.router, prefix="/api")
    app.include_router(segmentation.router, prefix="/api")
    app.include_router(dataset_api.router, prefix="/api")
    app.state.db_sessionmaker = maker
    app.state.job_store = job_store
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_optional_current_user] = lambda: owner
    monkeypatch.setattr(evidence.limiter, "enabled", False)
    monkeypatch.setattr(segmentation.limiter, "enabled", False)

    async def api_error(request, error):
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail, "error_code": error.error_code, **error.extra})

    app.add_exception_handler(APIError, api_error)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield app, client, maker
    finally:
        await shutdown_jobs(app)


async def test_research_returns_durable_admission_before_slow_planning(feature_jobs_http, monkeypatch):
    app, client, maker = feature_jobs_http
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def run(session, study, user_id=None, *, job=None, run_id=None):
        calls.append(job)
        started.set()
        await release.wait()
        assert job is not None
        row = await session.get(ResearchRuns, run_id)
        row.status = "completed"
        await job.fence(session)
        await session.commit()
        return row

    fake = SimpleNamespace(run_study_research=run)
    app.state.research_engine = fake
    monkeypatch.setattr(evidence, "ResearchEngineService", lambda **kwargs: fake)
    request = asyncio.create_task(client.post("/api/studies/feature-study/research", headers={"Idempotency-Key": "research-one"}))
    try:
        await asyncio.wait_for(started.wait(), 3)
        done, _ = await asyncio.wait({request}, timeout=0.5)
        assert request in done, "The HTTP request awaited the research provider instead of durable admission"
        response = request.result()
        assert response.status_code == 202
        accepted = response.json()
        assert accepted["job_id"] and accepted["id"]
        async with maker() as session:
            row = (await session.scalars(select(DurableJobs))).one()
            assert row.owner_id == "feature-owner"
            assert row.result_refs["run_id"] == accepted["id"]
        repeat = await client.post("/api/studies/feature-study/research", headers={"Idempotency-Key": "research-one"})
        assert repeat.json()["job_id"] == accepted["job_id"]
        assert len(calls) == 1
        # Without the key, a second request while the run is in flight is
        # refused: three parallel LLM pipelines for one study were admitted
        # live (2026-09-14) from a double click plus a reload.
        concurrent = await client.post("/api/studies/feature-study/research")
        assert concurrent.status_code == 409, concurrent.text
        assert concurrent.json()["error_code"] == "research_run_in_progress"
        assert len(calls) == 1
    finally:
        release.set()
        await asyncio.gather(request, return_exceptions=True)
        if getattr(app.state, "job_runtime", None) is not None:
            await app.state.job_runtime.drain()
    # Once the run has finished, a new run is admitted again.
    follow_up = await client.post("/api/studies/feature-study/research")
    assert follow_up.status_code == 202, follow_up.text
    if getattr(app.state, "job_runtime", None) is not None:
        await app.state.job_runtime.drain()


@pytest.mark.parametrize("newer_status", [None, "archived", "completed"])
async def test_research_completion_preserves_newer_study_revision(
    feature_jobs_http, monkeypatch, tmp_path, newer_status,
):
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.research import service as research_module

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(research_module, "_upload_dir", lambda: tmp_path / "research")
    reply = json.dumps({
        "business_idea": "Synthetic idea", "target_market": ["Synthetic participants"],
        "problem_areas": ["Synthetic need"], "behavioral_questions": ["How is it used?"],
        "economic_questions": ["What is affordable?"], "competition_questions": ["What alternatives exist?"],
        "market_questions": ["Who participates?"],
        "dataset_requirements": [{"category": "usage", "description": "Synthetic participation evidence"}],
        "summary": "A synthetic research plan for the fixture.",
        "queries": ["synthetic participants needs", "synthetic participants alternatives", "synthetic affordability"],
    })
    llm = SingleAdapterLLMService(FakeAdapter([
        FakeRoute(candidate=RouteCandidate(provider="fake", model="synthetic-research"), reply=reply),
    ]))
    started = asyncio.Event()
    release = asyncio.Event()
    requests = []
    complete = llm.complete

    async def held_complete(request):
        requests.append(request)
        if len(requests) == 1:
            started.set()
            await release.wait()
        return await complete(request)

    async def discover(**kwargs):
        assert not kwargs["session"].in_transaction()
        return [], []

    search_provider = create_autospec(research_module.SearchProvider, instance=True)
    search_provider.name = "empty-test-search"
    search_provider.search.return_value = []
    discovery_engine = create_autospec(research_module.DatasetDiscoveryEngine, instance=True)
    discovery_engine.discover_and_process_datasets.side_effect = discover
    monkeypatch.setattr(llm, "complete", held_complete)
    app.state.research_engine = research_module.ResearchEngineService(
        llm_service=llm, search_provider=search_provider,
        vector_engine=research_module.VectorSearchEngine(), discovery_engine=discovery_engine,
    )
    response = await client.post("/api/studies/feature-study/research", headers={"Idempotency-Key": "research-cas"})
    assert response.status_code == 202, response.text
    accepted = response.json()
    try:
        await asyncio.wait_for(started.wait(), 5)
        if newer_status is not None:
            async with maker() as session, session.begin():
                study = await session.get(Studies, "feature-study")
                study.status = newer_status
                study.step = 5
                study.findings = {"report_id": "newer-report"}
        release.set()
        await asyncio.wait_for(app.state.job_runtime.drain(), 10)
    finally:
        release.set()

    async with maker() as session:
        job = await session.get(DurableJobs, accepted["job_id"])
        run = await session.get(ResearchRuns, accepted["id"])
        study = await session.get(Studies, "feature-study")
        assert job.status == run.status == "completed", job.error
        assert study.status == (newer_status or "in_progress")
        assert study.revision == 2
        if newer_status is not None:
            assert study.findings == {"report_id": "newer-report"}
            assert study.step == 5
        assert job.input_data["study"]["revision"] == 1
        assert run.step_progress["summary"]["study_revision"] == 1
        assert run.step_progress["summary"]["study_projection_applied"] is (newer_status is None)
        checkpoints = list(await session.scalars(select(JobCheckpoints).where(JobCheckpoints.job_id == job.id)))
        assert checkpoints and all(checkpoint.status == "completed" for checkpoint in checkpoints)
    request_count = len(requests)
    polled = await client.get(f"/api/studies/feature-study/research/jobs/{accepted['job_id']}")
    detail = await client.get(f"/api/studies/feature-study/research/{accepted['id']}")
    assert polled.status_code == detail.status_code == 200
    assert len(requests) == request_count


async def test_segmentation_publishes_results_with_durable_checkpoint(feature_jobs_http, monkeypatch):
    app, client, maker = feature_jobs_http
    calls = []

    class FakeSegmentation:
        def __init__(self, session, llm_service=None):
            self.session = session

        async def run_segmentation(self, study_id, user_id=None, **kwargs):
            calls.append(study_id)
            row = SegmentationRuns(id="feature-segmentation", study_id=study_id, user_id=user_id, status="completed", segment_count=0)
            self.session.add(row)
            await self.session.commit()
            return row, []

    monkeypatch.setattr(segmentation, "SegmentationEngineService", FakeSegmentation)
    response = await client.post("/api/studies/feature-study/segmentation", json={"desired_clusters": 2}, headers={"Idempotency-Key": "segments-one"})
    assert response.status_code == 201
    result = response.json()
    assert result["run"]["id"] == "feature-segmentation"
    assert result["job_id"]
    async with maker() as session:
        job = await session.get(DurableJobs, result["job_id"])
        assert job.status == "completed" and job.owner_id == "feature-owner"
        checkpoint = (await session.scalars(select(JobCheckpoints).where(JobCheckpoints.job_id == job.id))).one()
        assert checkpoint.status == "completed"
        assert checkpoint.result_refs["run_id"] == "feature-segmentation"
    await shutdown_jobs(app)
    del app.state.job_runtime
    repeat = await client.post("/api/studies/feature-study/segmentation", json={"desired_clusters": 2}, headers={"Idempotency-Key": "segments-one"})
    assert repeat.json() == result
    assert len(calls) == 1


@pytest.mark.parametrize("outcome", ["completed", "changed", "cancelled"])
async def test_segmentation_closes_input_versions_and_preserves_terminal_fences(
    feature_jobs_http, monkeypatch, tmp_path, outcome,
):
    from bebshax.api.jobs import cancel_job_async
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.service import DatasetService
    from bebshax.jobs.store import SQLJobStore
    from bebshax.segmentation import service as segmentation_module

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    dataset_service = DatasetService(maker)
    await dataset_service.ingest_from_upload(
        ("age\n" + "\n".join(str(20 + index) for index in range(20)) + "\n").encode(),
        "synthetic.csv", "Synthetic segmentation source", user_id="feature-owner", study_id="feature-study",
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def interpret(**kwargs):
        started.set()
        await release.wait()
        return []

    monkeypatch.setattr(segmentation_module, "interpret_market_segments", interpret)
    if outcome == "changed":
        claim = app.state.job_store.claim

        async def change_before_claim(*args, **kwargs):
            async with maker() as session, session.begin():
                study = await session.get(Studies, "feature-study")
                study.prompt = "Newer segmentation context"
            return await claim(*args, **kwargs)

        monkeypatch.setattr(app.state.job_store, "claim", change_before_claim)
        release.set()
    pending = asyncio.create_task(client.post("/api/studies/feature-study/segmentation", json={"desired_clusters": 2}))
    remote = SimpleNamespace(state=SimpleNamespace(job_store=SQLJobStore(maker)))
    try:
        if outcome != "changed":
            await asyncio.wait_for(started.wait(), 5)
            if outcome == "cancelled":
                async with maker() as session:
                    job = (await session.scalars(select(DurableJobs))).one()
                    job_id = job.id
                await cancel_job_async(remote, job_id, kind="segmentation", scope_id="feature-study", user_id="feature-owner")
            release.set()
        response = await pending
        assert response.status_code == (201 if outcome == "completed" else 409), response.text
        if outcome == "changed":
            assert not started.is_set()
        async with maker() as session:
            job = (await session.scalars(select(DurableJobs))).one()
            job_id = job.id
            assert job.input_data["input_versions"]["datasets"][0]["version_id"]
        await client.get(f"/api/studies/feature-study/segmentation/jobs/{job_id}")
        async with maker() as session:
            runs = list(await session.scalars(select(SegmentationRuns)))
            if outcome == "changed":
                assert runs == []
            else:
                assert len(runs) == 1 and runs[0].status == outcome
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await shutdown_jobs(remote)


async def test_dataset_upload_is_fenced_checkpointed_and_idempotent(feature_jobs_http, monkeypatch, tmp_path):
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.datasets.service import DatasetService
    from bebshax.db.models import DatasetSources
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.fake import FakeAdapter

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    service = DatasetService(maker, llm=SingleAdapterLLMService(FakeAdapter([])))
    app.dependency_overrides[dataset_api._get_dataset_service] = lambda: service
    url = "/api/datasets/upload"
    payload = {"name": "Synthetic upload", "study_id": "feature-study"}
    headers = {"Idempotency-Key": "dataset-one"}
    first = await client.post(url, data=payload, files={"file": ("data.csv", b"age\n20\n", "text/csv")}, headers=headers)
    assert first.status_code == 201
    result = first.json()
    assert result["job_id"]
    async with maker() as session:
        job = await session.get(DurableJobs, result["job_id"])
        assert job.status == "completed" and job.owner_id == "feature-owner"
        assert job.result_refs["dataset_id"] == result["id"]
        checkpoint = (await session.scalars(select(JobCheckpoints).where(JobCheckpoints.job_id == job.id))).one()
        assert checkpoint.status == "completed"
        assert checkpoint.result_refs["version_id"]
        assert len(list(await session.scalars(select(DatasetVersions)))) == 1
    repeated = await client.post(url, data=payload, files={"file": ("data.csv", b"age\n20\n", "text/csv")}, headers=headers)
    assert repeated.status_code == 201 and repeated.json() == result
    conflict = await client.post(url, data=payload, files={"file": ("data.csv", b"age\n30\n", "text/csv")}, headers=headers)
    assert conflict.status_code == 409
    async with maker() as session:
        assert len(list(await session.scalars(select(DatasetSources)))) == 1
    await shutdown_jobs(app)
    del app.state.job_runtime
    polled = await client.get(f"/api/datasets/jobs/{result['job_id']}?kind=dataset_upload&scope_id=feature-study")
    assert polled.status_code == 200
    assert polled.json()["result"]["id"] == result["id"]


@pytest.mark.parametrize("operation_name", ["study-upload", "url", "study-url", "refresh", "study-refresh", "candidate"])
async def test_other_dataset_entrypoints_share_durable_admission(feature_jobs_http, monkeypatch, tmp_path, operation_name):
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.datasets.service import DatasetService
    from bebshax.db.models import DatasetCandidates, DatasetSources
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.fake import FakeAdapter
    from bebshax.research import service as research_module

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    monkeypatch.setattr(research_module, "_upload_dir", lambda: tmp_path / "uploads")
    service = DatasetService(maker, llm=SingleAdapterLLMService(FakeAdapter([])))
    app.dependency_overrides[dataset_api._get_dataset_service] = lambda: service

    async def fetch(url):
        return b"age\n25\n", "text/csv"

    async def fetch_resource(url, **kwargs):
        return b"age\n25\n", {"content_type": "text/csv", "url": url}

    monkeypatch.setattr(dataset_module, "safe_fetch_dataset_bytes", fetch)
    monkeypatch.setattr(research_module, "fetch_resource_bytes", fetch_resource)
    headers = {"Idempotency-Key": f"command-{operation_name}"}
    request_args: dict[str, Any] = {"headers": headers}
    if operation_name == "study-upload":
        url = "/api/studies/feature-study/datasets/upload"
        request_args.update(data={"name": "Synthetic"}, files={"file": ("data.csv", b"age\n25\n", "text/csv")})
    elif operation_name in {"url", "study-url"}:
        url = "/api/datasets/url" if operation_name == "url" else "/api/studies/feature-study/datasets/url"
        request_args["json"] = {"url": "https://example.test/synthetic.csv", "name": "Synthetic", "study_id": "feature-study"}
    elif operation_name in {"refresh", "study-refresh"}:
        dataset = await service.ingest_from_url("https://example.test/synthetic.csv", "Synthetic", user_id="feature-owner", study_id="feature-study")
        url = f"/api/datasets/{dataset.id}/refresh" if operation_name == "refresh" else f"/api/studies/feature-study/datasets/{dataset.id}/refresh"
    else:
        async with maker() as session, session.begin():
            session.add(DatasetCandidates(
                id="feature-candidate", study_id="feature-study", user_id="feature-owner", source="fixture", external_id="one",
                name="Synthetic", url="https://example.test/synthetic.csv", download_url="https://example.test/synthetic.csv", format="csv",
            ))
        url = "/api/studies/feature-study/datasets/candidates/feature-candidate/import"
    response = await client.post(url, **request_args)
    assert response.status_code in {200, 201}, response.text
    result = response.json()
    assert result["job_id"]
    async with maker() as session:
        job = await session.get(DurableJobs, result["job_id"])
        assert job.status == "completed" and job.owner_id == "feature-owner"
        checkpoint = (await session.scalars(select(JobCheckpoints).where(JobCheckpoints.job_id == job.id))).one()
        assert checkpoint.status == "completed"
        assert checkpoint.result_refs["dataset_id"] == result.get("id", result.get("imported_dataset_id"))
        assert len(list(await session.scalars(select(DatasetVersions)))) == 1
        assert len(list(await session.scalars(select(DatasetSources)))) == 1


@pytest.mark.parametrize("study_scoped", [False, True])
async def test_dataset_refresh_rejects_changed_input_after_admission_before_fetch(
    feature_jobs_http, monkeypatch, tmp_path, study_scoped,
):
    from sqlalchemy import update

    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.datasets.service import DatasetService
    from bebshax.db.models import DatasetSources

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    fetches = []

    async def fetch(url):
        fetches.append(url)
        return b"age\n25\n", "text/csv"

    monkeypatch.setattr(dataset_module, "safe_fetch_dataset_bytes", fetch)
    service = DatasetService(maker)
    app.dependency_overrides[dataset_api._get_dataset_service] = lambda: service
    dataset = await service.ingest_from_url(
        "https://example.test/original.csv", "Synthetic", user_id="feature-owner", study_id="feature-study",
    )
    fetches.clear()
    claim = app.state.job_store.claim

    async def change_before_claim(*args, **kwargs):
        async with maker() as session, session.begin():
            await session.execute(update(DatasetSources).where(DatasetSources.id == dataset.id).values(
                source_url="https://example.test/changed.csv",
            ))
        return await claim(*args, **kwargs)

    monkeypatch.setattr(app.state.job_store, "claim", change_before_claim)
    prefix = "/api/studies/feature-study/datasets" if study_scoped else "/api/datasets"
    response = await client.post(f"{prefix}/{dataset.id}/refresh", headers={"Idempotency-Key": "pinned-refresh"})

    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "dataset_input_changed"
    assert fetches == []
    async with maker() as session:
        job = (await session.scalars(select(DurableJobs))).one()
        assert job.status == "failed"
        assert len(list(await session.scalars(select(DatasetVersions)))) == 1


@pytest.mark.parametrize("study_scoped", [False, True])
@pytest.mark.parametrize("scenario", ["replay", "metadata-change"])
async def test_dataset_refresh_preserves_admitted_snapshot_through_publication(
    feature_jobs_http, monkeypatch, tmp_path, study_scoped, scenario,
):
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.datasets.service import DatasetService
    from bebshax.db.models import DatasetSources

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    content = b"age\n25\n"
    fetches = []
    mutate = False

    async def fetch(url):
        fetches.append(url)
        if mutate:
            async with maker() as session, session.begin():
                current = await session.get(DatasetSources, dataset.id)
                current.file_type = "json"
        return content, "text/csv"

    monkeypatch.setattr(dataset_module, "safe_fetch_dataset_bytes", fetch)
    service = DatasetService(maker)
    app.dependency_overrides[dataset_api._get_dataset_service] = lambda: service
    dataset = await service.ingest_from_url(
        "https://example.test/synthetic.csv", "Synthetic", user_id="feature-owner", study_id="feature-study",
    )
    content = b"age\n30\n"
    fetches.clear()
    mutate = scenario == "metadata-change"
    prefix = "/api/studies/feature-study/datasets" if study_scoped else "/api/datasets"
    path = f"{prefix}/{dataset.id}/refresh"
    headers = {"Idempotency-Key": "refresh-publication"}
    response = await client.post(path, headers=headers)
    if mutate:
        assert response.status_code == 409, response.text
        assert response.json()["error_code"] == "dataset_refresh_conflict"
        async with maker() as session:
            assert len(list(await session.scalars(select(DatasetVersions)))) == 1
            assert (await session.get(DatasetSources, dataset.id)).file_path == dataset.file_path
    else:
        assert response.status_code == 200 and response.json()["content_changed"] is True
        repeated = await client.post(path, headers=headers)
        assert repeated.status_code == 200, repeated.text
        assert repeated.json() == response.json()
        assert len(fetches) == 1
        async with maker() as session:
            assert len(list(await session.scalars(select(DatasetVersions)))) == 2
            assert len(list(await session.scalars(select(DurableJobs)))) == 1


async def test_dataset_persona_command_is_durable_and_checkpointed(feature_jobs_http, monkeypatch, tmp_path):
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.service import DatasetService
    from bebshax.db.models import Personas
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.base import RouteCandidate
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute

    app, client, maker = feature_jobs_http
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: tmp_path / "uploads")
    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="synthetic"), reply=json.dumps({
        "name": "Synthetic participant", "age": 25, "occupation": "Student", "description": "A synthetic test persona",
        "goals": [], "needs": [], "pain_points": [], "behaviors": [], "motivations": [], "personality_traits": [],
    }))])
    service = DatasetService(maker, llm=SingleAdapterLLMService(adapter))
    app.dependency_overrides[dataset_api._get_dataset_service] = lambda: service
    dataset = await service.ingest_from_upload(b"age,role\n25,Student\n", "synthetic.csv", "Synthetic", user_id="feature-owner", study_id="feature-study")
    response = await client.post(f"/api/datasets/{dataset.id}/generate-personas", json={"requested_count": 1, "study_id": "feature-study"}, headers={"Idempotency-Key": "persona-one"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["job_id"]
    async with maker() as session:
        job = await session.get(DurableJobs, result["job_id"])
        assert job.status == "completed" and job.owner_id == "feature-owner"
        checkpoint = (await session.scalars(select(JobCheckpoints).where(JobCheckpoints.job_id == job.id))).one()
        assert checkpoint.status == "completed"
        assert checkpoint.result_refs["run_id"] == result["run_id"]
        assert len(list(await session.scalars(select(Personas)))) == 1


async def test_research_restart_poll_marks_domain_run_interrupted(feature_jobs_http):
    from datetime import timedelta
    from sqlalchemy import update
    from bebshax.jobs.store import utcnow

    app, client, maker = feature_jobs_http

    async def prepare(session, job):
        session.add(ResearchRuns(
            id="restart-research", study_id="feature-study", user_id="feature-owner", status="building_research_plan",
            step_progress={"summary": {"job_id": job["job_id"]}},
        ))
        return {"run_id": "restart-research"}

    admitted = await app.state.job_store.admit(
        kind="research_generation", scope_id="feature-study", owner_id="feature-owner", input_data={}, prepare=prepare,
    )
    async with maker() as session, session.begin():
        await session.execute(update(DurableJobs).where(DurableJobs.id == admitted.job["job_id"]).values(lease_expires_at=utcnow() - timedelta(seconds=1)))
    response = await client.get(f"/api/studies/feature-study/research/jobs/{admitted.job['job_id']}")
    assert response.status_code == 200 and response.json()["state"] == "interrupted"
    run_response = await client.get("/api/studies/feature-study/research/restart-research")
    assert run_response.json()["status"] == "interrupted"
    async with maker() as session:
        run = await session.get(ResearchRuns, "restart-research")
        assert run.status == "interrupted" and run.completed_at is not None


async def test_segmentation_restart_poll_marks_domain_run_interrupted(feature_jobs_http):
    from datetime import timedelta
    from sqlalchemy import update
    from bebshax.jobs.store import utcnow

    app, client, maker = feature_jobs_http

    async def prepare(session, job):
        session.add(SegmentationRuns(
            id="restart-segmentation", study_id="feature-study", user_id="feature-owner", status="interpreting_segments",
            configuration={"job_id": job["job_id"]},
        ))
        return {"run_id": "restart-segmentation"}

    admitted = await app.state.job_store.admit(
        kind="segmentation", scope_id="feature-study", owner_id="feature-owner", input_data={}, prepare=prepare,
    )
    async with maker() as session, session.begin():
        await session.execute(update(DurableJobs).where(DurableJobs.id == admitted.job["job_id"]).values(lease_expires_at=utcnow() - timedelta(seconds=1)))
    response = await client.get(f"/api/studies/feature-study/segmentation/jobs/{admitted.job['job_id']}")
    assert response.status_code == 200 and response.json()["state"] == "interrupted"
    detail = await client.get("/api/studies/feature-study/segmentation/runs/restart-segmentation")
    assert detail.json()["status"] == "interrupted"
    async with maker() as session:
        run = await session.get(SegmentationRuns, "restart-segmentation")
        assert run.status == "interrupted" and run.completed_at is not None