from types import SimpleNamespace

import pytest

from bebshax.api.errors import APIError
from bebshax.jobs.store import SQLJobStore


async def test_inline_command_replays_saved_result_after_runtime_restart(job_store: SQLJobStore):
    from bebshax.api.jobs import run_job_inline, shutdown_jobs

    app = SimpleNamespace(state=SimpleNamespace(job_store=job_store))
    calls = []

    async def operation(job):
        calls.append(job["job_id"])
        await job.begin_item("saved", input_data={"revision": 1})
        await job.complete_item("saved", result_refs={"artifact_id": "artifact-one"})
        job["result_refs"] = {"artifact_id": "artifact-one"}
        return {"id": "artifact-one", "status": "ready"}

    arguments = dict(kind="dataset_upload", scope_id="study-one", user_id="owner-one", input_data={"sha256": "one"}, idempotency_key="upload-one", operation=operation)
    first = await run_job_inline(app, **arguments)
    await shutdown_jobs(app)
    restarted = SimpleNamespace(state=SimpleNamespace(job_store=SQLJobStore(job_store.sessionmaker)))
    try:
        repeated = await run_job_inline(restarted, **arguments)
        assert first == repeated
        assert first["id"] == "artifact-one"
        assert first["job_id"] == calls[0]
        assert len(calls) == 1
        with pytest.raises(APIError) as rejected:
            await run_job_inline(restarted, **{**arguments, "input_data": {"sha256": "changed"}})
        assert rejected.value.status_code == 409
        assert len(calls) == 1
    finally:
        await shutdown_jobs(restarted)


async def test_inline_command_preserves_exception_and_records_failure(job_store: SQLJobStore):
    from bebshax.api.jobs import run_job_inline, shutdown_jobs

    app = SimpleNamespace(state=SimpleNamespace(job_store=job_store))
    started = []

    async def operation(job):
        started.append(job["job_id"])
        raise APIError(422, "Synthetic invalid dataset.", error_code="dataset_invalid")

    try:
        with pytest.raises(APIError) as failure:
            await run_job_inline(app, kind="dataset_upload", scope_id="study-one", user_id="owner-one", input_data={}, operation=operation)
        assert failure.value.status_code == 422
        saved = await job_store.get(started[0], kind="dataset_upload", scope_id="study-one", owner_id="owner-one")
        assert saved["state"] == "failed"
    finally:
        await shutdown_jobs(app)


@pytest.mark.parametrize("memory", [False, True])
async def test_command_snapshot_replay_returns_an_independent_original_copy(job_store, memory):
    from bebshax.api.jobs import replay_job_input, shutdown_jobs
    from bebshax.jobs.memory import MemoryJobStore

    store = MemoryJobStore() if memory else job_store
    original = {"title": "Synthetic report", "input_versions": {"revision": 1}}
    await store.admit(
        kind="report_generation", scope_id="study-one", owner_id="owner-one",
        input_data=original, idempotency_key="original-command",
    )
    app = SimpleNamespace(state=SimpleNamespace(job_store=store))
    arguments = {
        "kind": "report_generation", "scope_id": "study-one", "user_id": "owner-one",
        "idempotency_key": "original-command", "snapshot_fields": frozenset({"input_versions"}),
        "input_data": {"title": "Synthetic report", "input_versions": {"revision": 2}},
    }
    try:
        replayed = await replay_job_input(app, **arguments)
        assert replayed == original
        replayed["input_versions"]["revision"] = 99
        assert await replay_job_input(app, **arguments) == original
        for changed in ({"idempotency_key": "new-command"}, {"user_id": "other-owner"}, {"idempotency_key": None}):
            assert await replay_job_input(app, **{**arguments, **changed}) == arguments["input_data"]
    finally:
        await shutdown_jobs(app)


@pytest.mark.parametrize("memory", [False, True])
@pytest.mark.parametrize("changed", ["kind", "scope_id", "title", "expired"])
async def test_command_snapshot_replay_rejects_changed_identity_or_expired_payload(job_store, memory, changed):
    from sqlalchemy import update

    from bebshax.api.jobs import replay_job_input, shutdown_jobs
    from bebshax.jobs.memory import MemoryJobStore
    from bebshax.jobs.orm import DurableJobs
    from bebshax.jobs.store import utcnow

    store = MemoryJobStore() if memory else job_store
    admitted = await store.admit(
        kind="report_generation", scope_id="study-one", owner_id="owner-one",
        input_data={"title": "Original", "input_versions": {"revision": 1}}, idempotency_key="original-command",
    )
    arguments = {
        "kind": "report_generation", "scope_id": "study-one", "user_id": "owner-one",
        "idempotency_key": "original-command", "snapshot_fields": frozenset({"input_versions"}),
        "input_data": {"title": "Original", "input_versions": {"revision": 2}},
    }
    if changed == "title":
        arguments["input_data"]["title"] = "Changed"
    elif changed == "expired":
        if memory:
            store.rows[admitted.job["job_id"]].payload_expired_at = utcnow()
        else:
            async with store.sessionmaker() as session, session.begin():
                await session.execute(update(DurableJobs).where(DurableJobs.id == admitted.job["job_id"]).values(payload_expired_at=utcnow()))
    else:
        arguments[changed] = "changed"
    app = SimpleNamespace(state=SimpleNamespace(job_store=store))
    try:
        with pytest.raises(APIError) as rejected:
            await replay_job_input(app, **arguments)
        assert rejected.value.status_code == 409
        assert rejected.value.error_code == ("job_payload_expired" if changed == "expired" else "job_idempotency_conflict")
    finally:
        await shutdown_jobs(app)