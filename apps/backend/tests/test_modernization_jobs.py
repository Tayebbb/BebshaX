from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base


@pytest.mark.asyncio
async def test_job_admission_survives_store_restart_and_rejects_changed_input(tmp_path):
    from bebshax.jobs.store import IdempotencyConflict, SQLJobStore

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'journal.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        first = SQLJobStore(maker)
        admission = await first.admit(
            kind="report_generation", scope_id="study_one", owner_id="owner_one",
            input_data={"title": "Findings"}, idempotency_key="request_one",
        )
        restarted = SQLJobStore(maker)
        repeated = await restarted.admit(
            kind="report_generation", scope_id="study_one", owner_id="owner_one",
            input_data={"title": "Findings"}, idempotency_key="request_one",
        )
        assert admission.created is True
        assert repeated.created is False
        assert repeated.job["job_id"] == admission.job["job_id"]
        fetched = await restarted.get(
            admission.job["job_id"], kind="report_generation",
            scope_id="study_one", owner_id="owner_one",
        )
        # get() additionally reports checkpoint progress on top of the admitted job.
        assert fetched == {**repeated.job, "checkpoints": [], "provider_outcome_unknown": False}
        with pytest.raises(IdempotencyConflict):
            await restarted.admit(
                kind="report_generation", scope_id="study_one", owner_id="owner_one",
                input_data={"title": "Different"}, idempotency_key="request_one",
            )
    finally:
        await engine.dispose()


@pytest.fixture
async def journal(tmp_path):
    from bebshax.jobs.store import SQLJobStore

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SQLJobStore(maker), SQLJobStore(maker)
    finally:
        await engine.dispose()


async def _admit(store, **overrides):
    return await store.admit(**{
        "kind": "simulation", "scope_id": "study_one", "owner_id": "owner_one",
        "input_data": {"scenario": "original"}, **overrides,
    })


async def test_shared_owner_admission_is_bounded_across_stores(journal):
    from bebshax.jobs.store import AdmissionLimit

    first, second = journal
    attempts = await asyncio.gather(
        *(_admit(first if index % 2 else second) for index in range(6)),
        return_exceptions=True,
    )
    assert sum(not isinstance(result, Exception) for result in attempts) == 3
    assert sum(isinstance(result, AdmissionLimit) for result in attempts) == 3
    assert (await _admit(second, owner_id="owner_two")).created


async def test_expired_worker_is_fenced_and_recovery_does_not_replay(journal):
    from bebshax.jobs.store import LeaseLost, utcnow

    first, restarted = journal
    admitted = await _admit(first, idempotency_key="stable")
    lease = await first.claim(admitted.job["job_id"], worker_id="old_worker", lease_s=30)
    assert lease is not None
    recovered = await restarted.recover(now=utcnow() + timedelta(seconds=31))
    assert recovered[0]["state"] == "interrupted"
    with pytest.raises(LeaseLost):
        await first.finish(lease, result={"wrong": True})
    repeated = await _admit(restarted, idempotency_key="stable")
    assert not repeated.created
    assert repeated.job["state"] == "interrupted"
    assert repeated.job["attempts"] == 1
    assert await restarted.claim(admitted.job["job_id"], worker_id="new_worker") is None


async def test_checkpoint_marks_uncertain_calls_and_completed_references(journal):
    from bebshax.jobs.store import IdempotencyConflict, UncertainItem

    first, second = journal
    admitted = await _admit(first)
    lease = await first.claim(admitted.job["job_id"], worker_id="worker")
    await first.begin_item(lease, "persona_one", input_data={"version": 1})
    with pytest.raises(UncertainItem):
        await second.begin_item(lease, "persona_one", input_data={"version": 1})
    with pytest.raises(IdempotencyConflict):
        await second.begin_item(lease, "persona_one", input_data={"version": 2})
    await first.complete_item(lease, "persona_one", result_refs={"result_id": "result_one"})
    checkpoint = await second.begin_item(lease, "persona_one", input_data={"version": 1})
    assert checkpoint["status"] == "completed"
    assert checkpoint["result_refs"] == {"result_id": "result_one"}
    await first.finish(lease, result={"completed": 1}, result_refs={"run_id": "run_one"})
    stored = await second.get(admitted.job["job_id"], kind="simulation", scope_id="study_one", owner_id="owner_one")
    assert stored["result_refs"] == {"run_id": "run_one"}
    assert stored["result"] == {"completed": 1}
    assert stored["status"] == "completed"
    assert await second.get(admitted.job["job_id"], kind="simulation", scope_id="study_one", owner_id="other_owner") is None


async def test_deadline_recovery_releases_admission(journal):
    from bebshax.jobs.store import utcnow

    first, second = journal
    for _ in range(3):
        await _admit(first, timeout_s=1)
    recovered = await second.recover(now=utcnow() + timedelta(seconds=2))
    assert len(recovered) == 3
    assert all(job["error_code"] == "job_timeout" for job in recovered)
    assert (await _admit(first)).created


async def test_preparation_failure_rolls_back_job_and_domain_write(journal):
    from sqlalchemy import select
    from bebshax.jobs.orm import DurableJobs, JobOwners

    first, _ = journal

    async def prepare(session, job):
        session.add(JobOwners(owner_id="domain_marker", revision=1))
        await session.flush()
        raise ValueError("preparation failed")

    with pytest.raises(ValueError, match="preparation failed"):
        await _admit(first, prepare=prepare)
    async with first.sessionmaker() as session:
        assert (await session.scalars(select(DurableJobs))).all() == []
        assert await session.get(JobOwners, "domain_marker") is None


async def test_runtime_admits_before_runner_and_reuses_completed_result(journal):
    from bebshax.jobs.runtime import JobRuntime

    first, second = journal
    runtime = JobRuntime(first)
    calls = []

    async def runner(job):
        persisted = await second.get(job["job_id"], kind="simulation", scope_id="study_one", owner_id="owner_one")
        assert persisted["attempts"] == 1
        calls.append(job["job_id"])
        job["result"] = {"artifact": "artifact_one"}

    job = await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner, idempotency_key="one")
    await runtime.drain()
    repeated = await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner, idempotency_key="one")
    assert repeated["result"] == {"artifact": "artifact_one"}
    assert calls == [job["job_id"]]
    await runtime.shutdown()


async def test_runtime_shutdown_cancels_and_drains_without_replay(journal):
    from bebshax.jobs.runtime import JobRuntime

    first, second = journal
    runtime = JobRuntime(first)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def runner(job):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    job = await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner)
    await asyncio.wait_for(entered.wait(), 2)
    await runtime.shutdown()
    assert cancelled.is_set()
    assert not runtime.tasks
    stored = await second.get(job["job_id"], kind="simulation", scope_id="study_one", owner_id="owner_one")
    assert stored["state"] == "cancelled"
    assert stored["finished_at"] is not None
    with pytest.raises(RuntimeError, match="shutting down"):
        await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner)


async def test_api_store_is_explicit_and_supports_dict_state(journal):
    from bebshax.api.errors import APIError
    from bebshax.api.jobs import get_job_async, start_job, start_job_async, shutdown_jobs

    first, second = journal
    app = SimpleNamespace(state={"db_sessionmaker": first.sessionmaker})

    async def runner(job):
        job["result"] = {"answer": 42}

    with pytest.raises(APIError) as caught:
        start_job(app, kind="simulation", scope_id="study_one", user_id="owner_one", runner=runner)
    assert caught.value.error_code == "async_job_admission_required"
    accepted = await start_job_async(app, kind="simulation", scope_id="study_one", user_id="owner_one", input_data={}, runner=runner)
    await app.state["job_runtime"].drain()
    restarted_app = SimpleNamespace(state={"db_sessionmaker": second.sessionmaker})
    persisted = await get_job_async(restarted_app, accepted["job_id"], kind="simulation", scope_id="study_one", user_id="owner_one")
    assert persisted["result"] == {"answer": 42}
    with pytest.raises(APIError) as missing:
        await start_job_async(SimpleNamespace(state={}), kind="simulation", scope_id="study_one", user_id="owner_one", input_data={}, runner=runner)
    assert missing.value.error_code == "job_store_unavailable"
    await shutdown_jobs(app)


async def test_explicit_memory_store_keeps_legacy_runner_shape():
    from bebshax.api.jobs import get_job, start_job, shutdown_jobs
    from bebshax.jobs.memory import MemoryJobStore

    app = SimpleNamespace(state={"job_store": MemoryJobStore()})

    async def runner(job):
        job["result"] = ["legacy"]

    job = start_job(app, kind="simulation", scope_id="study_one", user_id="owner_one", runner=runner)
    await app.state["job_runtime"].drain()
    assert get_job(app, job["job_id"], kind="simulation", scope_id="study_one")["result"] == ["legacy"]
    await shutdown_jobs(app)


async def test_shutdown_during_terminal_write_drains_persistence(journal, monkeypatch):
    from bebshax.jobs.runtime import JobRuntime

    first, second = journal
    runtime = JobRuntime(first)
    writing = asyncio.Event()
    release = asyncio.Event()
    finish = first.finish

    async def paused_finish(*args, **kwargs):
        writing.set()
        await release.wait()
        return await finish(*args, **kwargs)

    async def runner(job):
        job["result"] = {"saved": True}

    monkeypatch.setattr(first, "finish", paused_finish)
    admitted = await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner)
    await asyncio.wait_for(writing.wait(), 3)
    stopping = asyncio.create_task(runtime.shutdown())
    release.set()
    await stopping
    persisted = await second.get(admitted["job_id"], kind="simulation", scope_id="study_one", owner_id="owner_one")
    assert persisted["status"] == "completed"
    assert persisted["result"] == {"saved": True}


async def test_invalid_result_fails_durably_instead_of_staying_running(journal):
    from bebshax.jobs.runtime import JobRuntime

    first, second = journal
    runtime = JobRuntime(first)

    async def runner(job):
        job["result"] = float("nan")

    admitted = await runtime.start(kind="simulation", scope_id="study_one", owner_id="owner_one", input_data={}, runner=runner)
    await runtime.drain()
    persisted = await second.get(admitted["job_id"], kind="simulation", scope_id="study_one", owner_id="owner_one")
    assert persisted["status"] == "failed" and persisted["error_code"] == "job_result_invalid"
    assert persisted["finished_at"]
    await runtime.shutdown()