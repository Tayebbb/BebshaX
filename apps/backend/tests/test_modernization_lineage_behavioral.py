from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bebshax.interview.orm
import bebshax.memory.orm
from bebshax.behavioral.engine import BehavioralSimulationEngine
from bebshax.behavioral.orm import BehavioralInsights, BehavioralTestResults, BehavioralTestRuns, BehavioralTests
from bebshax.db.models import Base, EvidenceClaims, MarketSegments, Personas, Studies
from bebshax.interview.orm import InterviewInsights
from bebshax.llm import LLMRequest, LLMResult, SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.memory.service import MemoryRecord, MemoryService


@pytest.fixture
async def behavioral_lineage(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'behavioral.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Studies(id="behavior_study", title="Study", user_id="owner_one"))
        session.add(BehavioralTests(id="behavior_test", study_id="behavior_study", user_id="owner_one", name="Test", test_type="pricing_test"))
        for index in range(2):
            session.add(Personas(id=f"behavior_persona_{index}", study_id="behavior_study", owner_id="owner_one", user_id="owner_one", name=f"Persona {index}", version=1))
        await session.flush()
        session.add(BehavioralTestRuns(
            id="behavior_run", study_id="behavior_study", behavioral_test_id="behavior_test", user_id="owner_one",
            target_population_type="all", target_persona_ids=["behavior_persona_0", "behavior_persona_1"],
            scenario_snapshot={"title": "Price", "scenario_text": "Consider this service"},
            status="pending", persona_count=2,
        ))
        await session.commit()
    try:
        yield maker
    finally:
        await engine.dispose()


def _result(persona_id, *, status="completed"):
    return dict(
        persona_id=persona_id, persona_name=persona_id, persona_version=1,
        status=status, decision="positive", decision_label="Interested", probability=0.8,
        confidence="medium", confidence_score=0.7, reasoning_summary="Synthetic fixture",
        key_factors=[], motivators=["Useful"], objections=[], simulation_context_sources={}, interview_signals_used=[],
    )


class FakeLLM(SingleAdapterLLMService):
    def __init__(self, check: Callable[[LLMRequest], None] | None = None) -> None:
        super().__init__(FakeAdapter([FakeRoute(
            candidate=RouteCandidate(provider="fake", model="fake"), reply=json.dumps(_result("unused")),
        )]))
        self.check = check

    async def complete(self, request: LLMRequest) -> LLMResult:
        if self.check is not None:
            self.check(request)
        return await super().complete(request)


class FakeMemory(MemoryService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def retrieve(
        self, persona_id: str, query: str, k: int = 6, *, owner_id: str | None = None,
        conversation_id: str | None = None, min_relevance: float = 0,
        sources: tuple[str, ...] | None = None,
    ) -> list[MemoryRecord]:
        self.calls.append((persona_id, owner_id))
        return [MemoryRecord(
            id="memory-fixture", persona_id=persona_id, owner_id=owner_id, kind="observation",
            text="A synthetic past preference", importance=1, created_at=datetime.now(timezone.utc),
        )]


async def test_retry_replaces_current_insights_atomically_without_touching_history(behavioral_lineage, monkeypatch):
    maker = behavioral_lineage
    async with maker() as session:
        run = await session.get(BehavioralTestRuns, "behavior_run")
        run.status = "completed_with_warnings"
        session.add(BehavioralTestRuns(id="history_run", study_id="behavior_study", behavioral_test_id="behavior_test", user_id="owner_one", status="completed"))
        await session.flush()
        for index in range(2):
            session.add(BehavioralTestResults(
                id=f"existing_result_{index}", test_run_id="behavior_run", behavioral_test_id="behavior_test", study_id="behavior_study",
                **_result(f"behavior_persona_{index}", status="failed" if index else "completed"),
            ))
        for run_id in ("behavior_run", "history_run"):
            session.add(BehavioralInsights(
                id=f"insight_{run_id}", study_id="behavior_study", test_run_id=run_id, behavioral_test_id="behavior_test",
                user_id="owner_one", type="risk", title="Old risk", description="Old result", confidence=0.5,
            ))
        await session.commit()
    engine = BehavioralSimulationEngine(FakeLLM(), maker)
    calls = []

    async def simulation(**kwargs):
        calls.append(kwargs["persona"].id)
        return _result(kwargs["persona"].id)

    monkeypatch.setattr(engine, "_safe_simulate_single", simulation)
    run = await engine.retry_failed_simulations("behavior_run", study_id="behavior_study")
    assert calls == ["behavior_persona_1"]
    assert run.status == "completed"
    assert run.completed_count == 2 and run.failed_count == 0
    async with maker() as session:
        current = (await session.scalars(select(BehavioralInsights).where(BehavioralInsights.test_run_id == "behavior_run"))).all()
        assert [insight.type for insight in current] == ["opportunity"]
        assert await session.get(BehavioralInsights, "insight_history_run") is not None
        assert await session.get(BehavioralTestResults, "existing_result_0") is not None


async def test_behavioral_llm_runs_with_no_open_read_transaction(behavioral_lineage):
    maker = behavioral_lineage
    active = {}
    batch_task = asyncio.current_task()

    def begun(session, transaction, connection):
        active[session] = asyncio.current_task()

    def ended(session, transaction):
        if transaction.parent is None:
            active.pop(session, None)

    sync_class = maker.class_.sync_session_class
    event.listen(sync_class, "after_begin", begun)
    event.listen(sync_class, "after_transaction_end", ended)

    def check(request):
        assert not any(task in {batch_task, asyncio.current_task()} for task in active.values()), "A database transaction is held across the LLM request"

    try:
        run = await BehavioralSimulationEngine(FakeLLM(check), maker).execute_test_run("behavior_run", user_id="owner_one")
        assert run.status == "completed"
        assert run.completed_count == 2
    finally:
        event.remove(sync_class, "after_begin", begun)
        event.remove(sync_class, "after_transaction_end", ended)


async def test_cancelled_behavioral_run_is_persisted_terminal(behavioral_lineage, monkeypatch):
    maker = behavioral_lineage
    engine = BehavioralSimulationEngine(FakeLLM(), maker)
    entered = asyncio.Event()

    async def simulation(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(engine, "_safe_simulate_single", simulation)
    task = asyncio.create_task(engine.execute_test_run("behavior_run", user_id="owner_one"))
    await asyncio.wait_for(entered.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with maker() as session:
        run = await session.get(BehavioralTestRuns, "behavior_run")
        assert run.status in {"failed", "cancelled"}
        assert run.completed_at is not None


async def test_finished_persona_is_checkpointed_before_sibling_finishes(behavioral_lineage, monkeypatch):
    from bebshax.jobs.orm import JobCheckpoints
    from bebshax.jobs.runtime import JobRuntime
    from bebshax.jobs.store import SQLJobStore

    maker = behavioral_lineage
    async with maker().bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = SQLJobStore(maker)
    runtime = JobRuntime(store)
    engine = BehavioralSimulationEngine(FakeLLM(), maker)
    blocked = asyncio.Event()
    first_saved = asyncio.Event()
    original_complete = store.complete_item

    async def complete_item(*args, **kwargs):
        await original_complete(*args, **kwargs)
        kwargs["session"].info["checkpoint_saved"] = True

    def committed(session):
        if session.info.pop("checkpoint_saved", False):
            first_saved.set()

    async def simulation(**kwargs):
        if kwargs["persona"].id.endswith("_1"):
            blocked.set()
            await asyncio.Event().wait()
        return _result(kwargs["persona"].id)

    monkeypatch.setattr(store, "complete_item", complete_item)
    monkeypatch.setattr(engine, "_safe_simulate_single", simulation)
    event.listen(maker.class_.sync_session_class, "after_commit", committed)

    async def runner(job):
        await engine.execute_test_run("behavior_run", user_id="owner_one", job=job)

    await runtime.start(kind="behavioral_simulation", scope_id="behavior_study", owner_id="owner_one", input_data={}, runner=runner)
    try:
        await asyncio.wait_for(blocked.wait(), 3)
        await asyncio.wait_for(first_saved.wait(), 3)
        async with maker() as session:
            checkpoints = (await session.scalars(select(JobCheckpoints))).all()
            assert sorted(row.status for row in checkpoints) == ["completed", "started"]
    finally:
        await runtime.shutdown()
        event.remove(maker.class_.sync_session_class, "after_commit", committed)
    async with maker() as session:
        results = (await session.scalars(select(BehavioralTestResults))).all()
        assert [row.persona_id for row in results] == ["behavior_persona_0"]
        checkpoints = (await session.scalars(select(JobCheckpoints))).all()
        assert sorted(row.status for row in checkpoints) == ["completed", "uncertain"]


async def test_behavioral_run_rejects_another_owner_before_model_work(behavioral_lineage):
    engine = BehavioralSimulationEngine(FakeLLM(), behavioral_lineage)
    with pytest.raises(ValueError, match="owner"):
        await engine.execute_test_run("behavior_run", user_id="other_owner")
    async with behavioral_lineage() as session:
        assert (await session.get(BehavioralTestRuns, "behavior_run")).status == "pending"


@pytest.fixture
async def behavioral_http(behavioral_lineage, monkeypatch):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from httpx import ASGITransport, AsyncClient
    from bebshax.api import behavioral as api
    from bebshax.api.auth import get_current_user, get_optional_current_user
    from bebshax.api.deps import get_session
    from bebshax.api.errors import APIError
    from bebshax.api.jobs import shutdown_jobs
    from bebshax.auth.models import Users

    maker = behavioral_lineage
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.state.db_sessionmaker = maker
    owner = Users(id="owner_one", email="owner@example.test", full_name="Owner")
    app.dependency_overrides[get_optional_current_user] = lambda: owner
    app.dependency_overrides[get_current_user] = lambda: owner

    async def session_dependency():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = session_dependency
    monkeypatch.setattr(api.limiter, "enabled", False)

    async def error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "error_code": exc.error_code, **exc.extra})

    app.add_exception_handler(APIError, error_handler)
    app.state.behavioral_calls = []

    async def execute_test_run(run_id, user_id=None, **kwargs):
        app.state.behavioral_calls.append((run_id, user_id))
        async with maker() as session:
            run = await session.get(BehavioralTestRuns, run_id)
            run.status = "completed"
            await session.commit()
            return run

    app.state.behavioral_engine = SimpleNamespace(execute_test_run=execute_test_run)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield app, client, maker
    finally:
        await shutdown_jobs(app)


async def test_behavioral_http_admission_is_idempotent_and_scoped(behavioral_http):
    from bebshax.jobs.orm import DurableJobs

    app, client, maker = behavioral_http
    url = "/api/studies/behavior_study/behavioral-tests/behavior_test/runs"
    request = {"scenario_text": "Original scenario"}
    first = await client.post(url, json=request, headers={"Idempotency-Key": "scenario_one"})
    assert first.status_code == 201
    assert first.json()["job_id"]
    await app.state.job_runtime.drain()
    repeated = await client.post(url, json=request, headers={"Idempotency-Key": "scenario_one"})
    assert repeated.status_code == 201
    assert repeated.json()["id"] == first.json()["id"]
    assert len(app.state.behavioral_calls) == 1
    conflict = await client.post(url, json={"scenario_text": "Changed scenario"}, headers={"Idempotency-Key": "scenario_one"})
    assert conflict.status_code == 409
    async with maker() as session:
        job = (await session.scalars(select(DurableJobs))).one()
        assert job.result_refs["run_id"] == first.json()["id"]


async def test_behavioral_admission_counts_other_features_before_creating_run(behavioral_http):
    from bebshax.api.jobs import start_job_async

    app, client, maker = behavioral_http

    async def blocked(job):
        await asyncio.Event().wait()

    for index in range(3):
        await start_job_async(app, kind="report_generation", scope_id=f"other_{index}", user_id="owner_one", input_data={}, runner=blocked)
    response = await client.post("/api/studies/behavior_study/behavioral-tests/behavior_test/runs", json={"scenario_text": "Scenario"})
    assert response.status_code == 429
    async with maker() as session:
        assert [run.id for run in (await session.scalars(select(BehavioralTestRuns))).all()] == ["behavior_run"]


async def test_private_behavioral_run_is_not_public_with_demo_study(behavioral_http):
    from bebshax.api.auth import get_optional_current_user

    app, client, maker = behavioral_http
    async with maker() as session:
        study = await session.get(Studies, "behavior_study")
        study.is_demo = True
        await session.commit()
    app.dependency_overrides[get_optional_current_user] = lambda: None
    response = await client.get("/api/studies/behavior_study/behavioral-tests/runs/behavior_run")
    assert response.status_code == 404
    listed = await client.get("/api/studies/behavior_study/behavioral-tests")
    assert listed.json() == []
    detailed = await client.get("/api/studies/behavior_study/behavioral-tests/behavior_test")
    assert detailed.status_code == 404
    runs = await client.get("/api/studies/behavior_study/behavioral-tests/behavior_test/runs")
    assert runs.json() == []
    compared = await client.get("/api/studies/behavior_study/behavioral-tests/compare?run_ids=behavior_run")
    assert compared.json()["runs"] == []
    metrics = await client.get("/api/studies/behavior_study/behavioral-tests/metrics")
    assert metrics.json()["total_runs"] == metrics.json()["total_tests"] == 0


@pytest.mark.parametrize("population", ["selected_personas", "segment"])
async def test_behavioral_does_not_expand_an_empty_selected_population(behavioral_http, population):
    _, client, _ = behavioral_http
    response = await client.post(
        "/api/studies/behavior_study/behavioral-tests/behavior_test/runs",
        json={"scenario_text": "Scenario", "target_population_type": population},
    )
    assert response.status_code == 422


async def test_memory_receives_verified_behavioral_owner(behavioral_lineage):
    maker = behavioral_lineage
    memory = FakeMemory()

    def check(request):
        assert "A synthetic past preference" in request.messages[1].content

    run = await BehavioralSimulationEngine(FakeLLM(check), maker, memory=memory).execute_test_run("behavior_run", user_id="owner_one")
    assert run.status == "completed"
    assert sorted(memory.calls) == [("behavior_persona_0", "owner_one"), ("behavior_persona_1", "owner_one")]


async def test_retry_insight_failure_rolls_back_new_results(behavioral_lineage, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    maker = behavioral_lineage
    async with maker() as session:
        run = await session.get(BehavioralTestRuns, "behavior_run")
        run.status = "failed"
        session.add(BehavioralTestResults(id="failed_result", test_run_id="behavior_run", behavioral_test_id="behavior_test", study_id="behavior_study", **_result("behavior_persona_0", status="failed")))
        session.add(BehavioralInsights(id="retained_old_insight", study_id="behavior_study", test_run_id="behavior_run", behavioral_test_id="behavior_test", type="risk", title="Old", description="Old", confidence=0.2))
        await session.commit()
    engine = BehavioralSimulationEngine(FakeLLM(), maker)

    async def simulation(**kwargs):
        return _result(kwargs["persona"].id)

    def fail_insight(session, flush_context, instances):
        if any(isinstance(row, BehavioralInsights) for row in session.new):
            raise SQLAlchemyError("Synthetic insight persistence failure")

    monkeypatch.setattr(engine, "_safe_simulate_single", simulation)
    sync_class = maker.class_.sync_session_class
    event.listen(sync_class, "before_flush", fail_insight)
    try:
        with pytest.raises(SQLAlchemyError):
            await engine.retry_failed_simulations("behavior_run", study_id="behavior_study", user_id="owner_one")
    finally:
        event.remove(sync_class, "before_flush", fail_insight)
    async with maker() as session:
        assert (await session.get(BehavioralTestResults, "failed_result")).status == "failed"
        assert await session.get(BehavioralInsights, "retained_old_insight") is not None


async def test_retry_endpoint_admits_a_durable_job(behavioral_http):
    app, client, maker = behavioral_http
    async with maker() as session:
        run = await session.get(BehavioralTestRuns, "behavior_run")
        run.status = "failed"
        await session.commit()

    async def retry(run_id, **kwargs):
        return await app.state.behavioral_engine.execute_test_run(run_id, **kwargs)

    app.state.behavioral_engine.retry_failed_simulations = retry
    url = "/api/studies/behavior_study/behavioral-tests/runs/behavior_run/retry-failed"
    first = await client.post(url, headers={"Idempotency-Key": "retry_one"})
    assert first.status_code == 202
    assert first.json()["job_id"]
    await app.state.job_runtime.drain()
    repeated = await client.post(url, headers={"Idempotency-Key": "retry_one"})
    assert repeated.status_code == 202
    assert repeated.json()["job_id"] == first.json()["job_id"]
    assert len(app.state.behavioral_calls) == 1


async def test_behavioral_context_preserves_all_owned_evidence_and_excludes_other_owners(behavioral_lineage):
    maker = behavioral_lineage
    async with maker() as session, session.begin():
        persona = await session.get(Personas, "behavior_persona_0")
        persona.segment_id = "context_segment"
        persona.dataset_refs = [{"name": f"Dataset {index}", "variable_distributions": {"tail": f"dataset_value_{index}"}} for index in range(3)]
        session.add(MarketSegments(
            id="context_segment", study_id="behavior_study", user_id="owner_one", segmentation_run_id="segment_run",
            name="Synthetic segment", description="Synthetic context fixture", population_percentage=100,
            characteristics={f"feature_{index}": f"segment_value_{index}" for index in range(6)},
        ))
        for index in range(7):
            session.add(InterviewInsights(
                id=f"context_insight_{index}", interview_id="context_conversation", study_id="behavior_study", user_id="owner_one",
                persona_id=persona.id, type="need", title=f"insight_title_{index}", description=f"insight_detail_{index}",
            ))
        for index in range(6):
            session.add(EvidenceClaims(
                id=f"context_claim_{index}", study_id="behavior_study", user_id="owner_one",
                claim_text=f"claim_detail_{index}", category="need", confidence=0.5,
            ))
        session.add(InterviewInsights(
            id="foreign_insight", interview_id="foreign_conversation", study_id="behavior_study", user_id="other_owner",
            persona_id=persona.id, type="need", title="foreign_insight_title", description="foreign_insight_detail",
        ))
        session.add(EvidenceClaims(
            id="foreign_claim", study_id="behavior_study", user_id="other_owner",
            claim_text="foreign_claim_detail", category="need", confidence=1,
        ))
    async with maker() as session:
        persona = await session.get(Personas, "behavior_persona_0")
        study = await session.get(Studies, "behavior_study")
        context, _, signals = await BehavioralSimulationEngine(FakeLLM(), maker)._gather_simulation_context(session, persona, study)
    for index in range(7):
        assert f"insight_detail_{index}" in context
        assert f"insight_title_{index}" in signals
    for index in range(6):
        assert f"claim_detail_{index}" in context
        assert f"segment_value_{index}" in context
    assert "dataset_value_2" in context
    assert "foreign_insight" not in context
    assert "foreign_claim" not in context


@pytest.mark.parametrize("legacy_state", ["pending", "running", "retry_pending"])
async def test_legacy_behavioral_cancel_fences_persisted_execution(behavioral_http, legacy_state):
    _, client, maker = behavioral_http
    async with maker() as session, session.begin():
        run = await session.get(BehavioralTestRuns, "behavior_run")
        run.status = legacy_state
        run.execution_token = "legacy-execution"
    response = await client.post("/api/studies/behavior_study/behavioral-tests/runs/behavior_run/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    async with maker() as session:
        run = await session.get(BehavioralTestRuns, "behavior_run")
        assert run.status == "cancelled" and run.execution_token is None
        assert run.completed_at is not None


async def test_behavioral_rejects_a_persona_version_changed_after_admission(behavioral_lineage):
    maker = behavioral_lineage
    async with maker() as session, session.begin():
        run = await session.get(BehavioralTestRuns, "behavior_run")
        run.input_manifest = {"personas": [{"id": f"behavior_persona_{index}", "version": 1} for index in range(2)]}
        persona = await session.get(Personas, "behavior_persona_0")
        persona.version = 2
    requests = []
    engine = BehavioralSimulationEngine(FakeLLM(requests.append), maker)
    with pytest.raises(ValueError, match="version|population"):
        await engine.execute_test_run("behavior_run", user_id="owner_one")
    assert requests == []


async def test_behavioral_drains_siblings_after_checkpoint_failure(behavioral_lineage, monkeypatch):
    engine = BehavioralSimulationEngine(FakeLLM(), behavioral_lineage)
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    siblings = []

    async def simulation(**kwargs):
        if kwargs["persona"].id.endswith("_0"):
            await entered.wait()
            raise RuntimeError("Synthetic checkpoint failure")
        siblings.append(asyncio.current_task())
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(engine, "_simulate_checkpointed", simulation)
    try:
        with pytest.raises(RuntimeError, match="Synthetic checkpoint failure"):
            await engine.execute_test_run("behavior_run", user_id="owner_one")
        assert cancelled.is_set(), "A failed run left an unregistered sibling provider task running"
        assert all(task.done() for task in siblings)
    finally:
        for task in siblings:
            task.cancel()
        await asyncio.gather(*siblings, return_exceptions=True)