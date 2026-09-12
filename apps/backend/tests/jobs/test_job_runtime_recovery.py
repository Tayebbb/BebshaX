import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from bebshax.jobs.runtime import JobRuntime
from bebshax.jobs.store import SQLJobStore


async def test_shutdown_after_claim_commit_only_interrupts_own_jobs(job_store: SQLJobStore, monkeypatch) -> None:
    foreign = await job_store.admit(kind="research", scope_id="study-2", owner_id="owner-2", input_data={})
    foreign_lease = await job_store.claim(foreign.job["job_id"], worker_id="foreign-worker")
    claimed = asyncio.Event()
    claim = job_store.claim

    async def pause_after_claim(*args, **kwargs):
        lease = await claim(*args, **kwargs)
        claimed.set()
        await asyncio.Event().wait()
        return lease

    monkeypatch.setattr(job_store, "claim", pause_after_claim)
    runtime = JobRuntime(job_store)

    async def runner(job):
        raise AssertionError("Claim was cancelled before the runner started")

    accepted = await runtime.start(kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner)
    await asyncio.wait_for(claimed.wait(), timeout=2)
    await runtime.shutdown()
    saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
    assert saved["state"] == "interrupted"
    untouched = await job_store.get(foreign.job["job_id"], kind="research", scope_id="study-2", owner_id="owner-2")
    assert untouched["state"] == "running"
    await job_store.finish(foreign_lease)


async def test_prepared_jobs_belong_to_runtime_before_launch(job_store: SQLJobStore) -> None:
    from bebshax.api.jobs import prepare_job, shutdown_jobs

    app = SimpleNamespace(state=SimpleNamespace(job_store=job_store))
    admitted = await prepare_job(
        app, kind="research", scope_id="study-1", user_id="owner-1", input_data={}, input_revision="study:2",
    )
    await shutdown_jobs(app)
    saved = await job_store.get(admitted.job["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
    assert saved["state"] == "cancelled"
    with pytest.raises(Exception) as rejected:
        await prepare_job(app, kind="research", scope_id="study-1", user_id="owner-1", input_data={})
    assert rejected.value.error_code == "job_runtime_closing"


async def test_initialize_registers_owned_tasks_and_close_hook(job_store: SQLJobStore) -> None:
    from bebshax.api.jobs import initialize_jobs, start_job_async

    registered_tasks = []
    registered_resources = []
    app = SimpleNamespace(state=SimpleNamespace(
        job_store=job_store, register_runtime_task=registered_tasks.append,
        register_runtime_resource=registered_resources.append,
    ))
    runtime = await initialize_jobs(app)

    async def runner(job):
        job["result"] = {"saved": True}

    try:
        accepted = await start_job_async(
            app, kind="research", scope_id="study-1", user_id="owner-1", input_data={},
            input_revision="study:7", runner=runner,
        )
        await runtime.drain()
        assert runtime is await initialize_jobs(app)
        assert registered_resources == [runtime]
        assert registered_tasks
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "completed"
        assert saved["input_revision"] == "study:7"
    finally:
        await runtime.aclose()
    assert all(task.done() for task in registered_tasks)


async def test_cross_runtime_cancel_is_seen_by_live_worker(job_store: SQLJobStore) -> None:
    from bebshax.api.jobs import cancel_job_async

    running = asyncio.Event()
    runtime = JobRuntime(job_store, lease_s=0.3)

    async def runner(job):
        running.set()
        await asyncio.Event().wait()

    accepted = await runtime.start(kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner)
    try:
        await asyncio.wait_for(running.wait(), timeout=2)
        other_app = SimpleNamespace(state=SimpleNamespace(job_store=SQLJobStore(job_store.sessionmaker)))
        cancelled = await cancel_job_async(other_app, accepted["job_id"], kind="research", scope_id="study-1", user_id="owner-1")
        assert cancelled["state"] == "cancelled"
        await asyncio.wait_for(runtime.drain(), timeout=2)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "cancelled"
    finally:
        await runtime.shutdown()


async def test_shutdown_is_bounded_when_runner_suppresses_cancellation(job_store: SQLJobStore) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    runtime = JobRuntime(job_store)

    async def runner(job):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()

    accepted = await runtime.start(kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner)
    await asyncio.wait_for(started.wait(), timeout=2)
    try:
        with pytest.raises(RuntimeError, match="did not stop"):
            await runtime.shutdown(timeout_s=0.02)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "interrupted"
    finally:
        release.set()
        await asyncio.wait_for(runtime.drain(), timeout=2)
        await runtime.shutdown()


async def test_runner_await_does_not_hold_journal_connection(job_store: SQLJobStore, journal_engine) -> None:
    checked_out = {"count": 0}

    @event.listens_for(journal_engine.sync_engine, "checkout")
    def checkout(connection, record, proxy):
        checked_out["count"] += 1

    @event.listens_for(journal_engine.sync_engine, "checkin")
    def checkin(connection, record):
        checked_out["count"] -= 1

    async def runner(job):
        assert checked_out["count"] == 0
        await asyncio.sleep(0)
        assert checked_out["count"] == 0
        job["result"] = {"saved": True}

    runtime = JobRuntime(job_store)
    try:
        accepted = await runtime.start(kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner)
        await asyncio.wait_for(runtime.drain(), timeout=2)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "completed"
    finally:
        await runtime.shutdown()


async def test_heartbeat_failure_is_interruption_not_user_cancellation(job_store: SQLJobStore, monkeypatch) -> None:
    async def unavailable(lease):
        raise RuntimeError("Synthetic journal interruption")

    monkeypatch.setattr(job_store, "heartbeat", unavailable)
    runtime = JobRuntime(job_store, lease_s=0.9)

    async def runner(job):
        await asyncio.Event().wait()

    try:
        accepted = await runtime.start(kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner)
        await asyncio.wait_for(runtime.drain(), 2)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "interrupted"
        assert saved["error_code"] == "job_interrupted"
    finally:
        await runtime.shutdown()


async def test_live_timeout_persists_terminal_state(job_store: SQLJobStore) -> None:
    runtime = JobRuntime(job_store)

    async def runner(job):
        await asyncio.Event().wait()

    try:
        accepted = await runtime.start(
            kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner, timeout_s=0.2,
        )
        await asyncio.wait_for(runtime.drain(), 2)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == "timed_out"
        assert saved["error_code"] == "job_timeout"
    finally:
        await runtime.shutdown()


@pytest.mark.parametrize("cause, expected_state", [("shutdown", "cancelled"), ("heartbeat", "interrupted")])
async def test_suppressed_worker_cancellation_cannot_publish_success(job_store: SQLJobStore, monkeypatch, cause, expected_state) -> None:
    started = asyncio.Event()
    runtime = JobRuntime(job_store, lease_s=0.6)

    async def unavailable(lease):
        raise RuntimeError("Synthetic journal interruption")

    if cause == "heartbeat":
        monkeypatch.setattr(job_store, "heartbeat", unavailable)

    async def runner(job):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            job["result"] = {"must_not_be_acknowledged": True}

    try:
        accepted = await runtime.start(
            kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, runner=runner,
        )
        await asyncio.wait_for(started.wait(), 2)
        if cause == "shutdown":
            await runtime.shutdown()
        else:
            await asyncio.wait_for(runtime.drain(), 2)
        saved = await job_store.get(accepted["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
        assert saved["state"] == expected_state
        assert saved["error_code"] == f"job_{expected_state}"
        assert saved["result"] is None
    finally:
        await runtime.shutdown()


async def test_concurrent_worker_cleanup_does_not_deadlock_sqlite(job_store: SQLJobStore) -> None:
    admissions = [await job_store.admit(
        kind="research", scope_id=f"study-{index}", owner_id=f"owner-{index}",
        input_data={}, worker_id=f"worker-{index}",
    ) for index in range(3)]
    outcomes = await asyncio.gather(*(
        job_store.interrupt_worker(f"worker-{index}") for index in range(3)
    ), return_exceptions=True)
    assert not any(isinstance(outcome, BaseException) for outcome in outcomes), outcomes
    for index, admitted in enumerate(admissions):
        saved = await job_store.get(admitted.job["job_id"], kind="research", scope_id=f"study-{index}", owner_id=f"owner-{index}")
        assert saved["state"] == "cancelled"


async def test_shutdown_during_multiple_claims_releases_every_transaction(job_store: SQLJobStore) -> None:
    runtime = JobRuntime(job_store)

    async def blocked(job):
        await asyncio.Event().wait()

    accepted = [await runtime.start(
        kind="research", scope_id=f"study-{index}", owner_id="owner-one", input_data={}, runner=blocked,
    ) for index in range(3)]
    await runtime.shutdown()
    assert not runtime.tasks
    for index, job in enumerate(accepted):
        saved = await job_store.get(job["job_id"], kind="research", scope_id=f"study-{index}", owner_id="owner-one")
        assert saved["state"] in {"cancelled", "interrupted"}


async def test_active_job_without_a_lease_expiry_is_recovered(job_store: SQLJobStore) -> None:
    from sqlalchemy import update
    from bebshax.jobs.orm import DurableJobs

    admission = await job_store.admit(kind="research", scope_id="study-one", owner_id="owner-one", input_data={})
    async with job_store.sessionmaker() as session, session.begin():
        await session.execute(update(DurableJobs).where(DurableJobs.id == admission.job["job_id"]).values(lease_expires_at=None))
    recovered = await job_store.recover(owner_id="owner-one")
    assert [job["job_id"] for job in recovered] == [admission.job["job_id"]]
    assert recovered[0]["state"] == "interrupted"

async def test_runtime_is_rebuilt_when_the_app_database_binding_changes(tmp_path) -> None:
    """A cached SQL job store bound to a replaced sessionmaker must not keep writing
    to the old (possibly disposed) engine; the runtime follows app.state.db_sessionmaker."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bebshax.api.jobs import job_runtime
    from bebshax.jobs.memory import MemoryJobStore
    from bebshax.jobs.orm import Base as JobsBase

    async def make_sessions(name: str):
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(JobsBase.metadata.create_all)
        return engine, async_sessionmaker(engine, expire_on_commit=False)

    first_engine, first_sessions = await make_sessions("first.sqlite")
    second_engine, second_sessions = await make_sessions("second.sqlite")
    try:
        app = SimpleNamespace(state=SimpleNamespace(db_sessionmaker=first_sessions))
        first_runtime = job_runtime(app)
        assert first_runtime is job_runtime(app)
        assert first_runtime.store.sessionmaker is first_sessions

        await first_engine.dispose()
        app.state.db_sessionmaker = second_sessions
        second_runtime = job_runtime(app)
        assert second_runtime is not first_runtime
        assert second_runtime.store.sessionmaker is second_sessions
        admitted = await second_runtime.prepare(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
        assert admitted.created

        # An explicitly injected memory store has no DB binding and is never replaced.
        memory_app = SimpleNamespace(state=SimpleNamespace(job_store=MemoryJobStore(), db_sessionmaker=first_sessions))
        memory_runtime = job_runtime(memory_app)
        memory_app.state.db_sessionmaker = second_sessions
        assert job_runtime(memory_app) is memory_runtime
    finally:
        await second_engine.dispose()
