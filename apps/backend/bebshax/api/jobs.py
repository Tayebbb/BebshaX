"""Job API adapters. SQL admission must be awaited before returning an accepted response."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import copy
from typing import Any, Optional

from sqlalchemy import select

from bebshax.api.errors import APIError
from bebshax.jobs.memory import MemoryJobStore
from bebshax.jobs.orm import DurableJobs
from bebshax.jobs.runtime import JobContext, JobRuntime, Prepare, Runner, RuntimeClosing
from bebshax.jobs.store import (
    MAX_RUNNING_JOBS_PER_USER, Admission, AdmissionLimit, IdempotencyConflict, SQLJobStore,
)


def _state_get(app: Any, name: str, default: Any = None) -> Any:
    return app.state.get(name, default) if isinstance(app.state, dict) else getattr(app.state, name, default)


def _state_set(app: Any, name: str, value: Any) -> None:
    if isinstance(app.state, dict):
        app.state[name] = value
    else:
        setattr(app.state, name, value)


def job_runtime(app: Any) -> JobRuntime:
    runtime = _state_get(app, "job_runtime")
    maker = _state_get(app, "db_sessionmaker")
    if runtime is not None:
        # A cached SQL store bound to a replaced sessionmaker would write to a
        # disposed engine; rebuild against the app's current database binding.
        store = runtime.store
        if not (isinstance(store, SQLJobStore) and maker is not None and store.sessionmaker is not maker):
            return runtime
        # Stop the stale runtime's recovery/heartbeat tasks so nothing keeps
        # polling the replaced (possibly disposed) engine.
        runtime._closing = True
        for task in (*runtime.tasks, runtime._recovery_task):
            if task is not None and not task.done():
                task.cancel()
        _state_set(app, "job_store", None)
        _state_set(app, "job_runtime", None)
    store = _state_get(app, "job_store")
    if store is None:
        if maker is None:
            raise APIError(503, "Durable job storage is not configured.", error_code="job_store_unavailable")
        store = SQLJobStore(maker)
    if not isinstance(store, (SQLJobStore, MemoryJobStore)):
        raise APIError(503, "Invalid job store configuration.", error_code="job_store_unavailable")
    runtime = JobRuntime(store, register_task=_state_get(app, "register_runtime_task"))
    _state_set(app, "job_store", store)
    _state_set(app, "job_runtime", runtime)
    _state_set(app, "async_job_tasks", runtime.tasks)
    register_resource = _state_get(app, "register_runtime_resource")
    if callable(register_resource):
        register_resource(runtime)
    return runtime


def _admission_error(exc: Exception) -> APIError:
    if isinstance(exc, RuntimeClosing):
        return APIError(503, "Job runtime is shutting down.", error_code="job_runtime_closing")
    if isinstance(exc, AdmissionLimit):
        return APIError(429, str(exc), error_code="too_many_jobs", extra={"max_running_jobs": MAX_RUNNING_JOBS_PER_USER})
    return APIError(409, str(exc), error_code="job_idempotency_conflict")


async def replay_job_input(
    app: Any, *, kind: str, scope_id: str, user_id: str, idempotency_key: str | None,
    input_data: dict[str, Any], snapshot_fields: frozenset[str],
) -> dict[str, Any]:
    if idempotency_key is None:
        return input_data
    store = job_runtime(app).store
    if isinstance(store, SQLJobStore):
        async with store.sessionmaker() as session:
            existing = await session.scalar(select(DurableJobs).where(
                DurableJobs.owner_id == user_id, DurableJobs.idempotency_key == idempotency_key,
            ))
    else:
        existing = next((row for row in store.rows.values() if (
            row.owner_id == user_id and row.idempotency_key == idempotency_key
        )), None)
    if existing is None:
        return input_data
    if (existing.kind, existing.scope_id) != (kind, scope_id):
        raise _admission_error(IdempotencyConflict("This idempotency key belongs to a different command."))
    if existing.payload_expired_at is not None or existing.input_data is None:
        raise APIError(409, "The saved command payload has expired.", error_code="job_payload_expired", extra={"job_id": existing.id})
    command = {name: value for name, value in input_data.items() if name not in snapshot_fields}
    original = {name: value for name, value in existing.input_data.items() if name not in snapshot_fields}
    if command != original:
        raise _admission_error(IdempotencyConflict("This idempotency key was already used with different input."))
    return copy.deepcopy(existing.input_data)


async def prepare_job(
    app: Any, *, kind: str, scope_id: str, user_id: str, input_data: dict[str, Any],
    idempotency_key: str | None = None, timeout_s: float | None = None,
    input_revision: str | None = None,
    job_id_prefix: str = "job", prepare: Prepare | None = None,
) -> Admission:
    try:
        return await job_runtime(app).prepare(
            kind=kind, scope_id=scope_id, owner_id=user_id, input_data=input_data,
            idempotency_key=idempotency_key, timeout_s=timeout_s,
            input_revision=input_revision,
            job_id_prefix=job_id_prefix, prepare=prepare,
        )
    except (AdmissionLimit, IdempotencyConflict, RuntimeClosing) as exc:
        raise _admission_error(exc) from exc


async def start_job_async(
    app: Any, *, kind: str, scope_id: str, runner: Runner, user_id: str,
    input_data: dict[str, Any], idempotency_key: str | None = None,
    input_revision: str | None = None,
    user_safe_exceptions: tuple[type[BaseException], ...] = (),
    timeout_s: float | None = None, job_id_prefix: str = "job", prepare: Prepare | None = None,
) -> dict[str, Any]:
    try:
        return await job_runtime(app).start(
            kind=kind, scope_id=scope_id, owner_id=user_id, runner=runner, input_data=input_data,
            idempotency_key=idempotency_key, user_safe_exceptions=user_safe_exceptions,
            input_revision=input_revision,
            timeout_s=timeout_s, job_id_prefix=job_id_prefix, prepare=prepare,
        )
    except (AdmissionLimit, IdempotencyConflict, RuntimeClosing) as exc:
        raise _admission_error(exc) from exc


async def run_job_inline(
    app: Any, *, kind: str, scope_id: str, user_id: str, input_data: dict[str, Any],
    operation: Callable[[JobContext], Awaitable[dict[str, Any]]],
    idempotency_key: str | None = None, input_revision: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    failures: list[Exception] = []

    async def runner(job: JobContext) -> None:
        try:
            result = await operation(job)
            job["result"] = {**result, "job_id": job["job_id"]}
        except Exception as exc:
            failures.append(exc)
            raise

    accepted = await start_job_async(
        app, kind=kind, scope_id=scope_id, user_id=user_id, input_data=input_data,
        runner=runner, idempotency_key=idempotency_key, input_revision=input_revision, timeout_s=timeout_s,
    )
    await job_runtime(app).wait(accepted["job_id"])
    saved = await get_job_async(app, accepted["job_id"], kind=kind, scope_id=scope_id, user_id=user_id)
    if failures and (saved is None or saved["state"] == "failed"):
        raise failures[0]
    if saved is not None and saved["state"] == "completed" and isinstance(saved["result"], dict):
        return saved["result"]
    state = saved["state"] if saved is not None else "unavailable"
    raise APIError(
        409 if state in {"queued", "running", "cancelled", "interrupted"} else 503,
        "Inspect the saved job status before explicitly retrying this command.",
        error_code=f"job_{state}", extra={"job_id": accepted["job_id"], "state": state},
    )


def start_job(
    app: Any, *, kind: str, scope_id: str, runner: Runner, user_id: Optional[str] = None,
    user_safe_exceptions: tuple[type[BaseException], ...] = (), timeout_s: float | None = None,
    job_id_prefix: str = "job", admission: Admission | None = None,
) -> dict[str, Any]:
    runtime = job_runtime(app)
    if user_id is None:
        raise APIError(401, "Sign in to start a background job.", error_code="unauthorized")
    if admission is not None:
        job = admission.job
        if (job["kind"], job["scope_id"], job["user_id"]) != (kind, scope_id, user_id):
            raise ValueError("Prepared admission does not match the caller's scope.")
        return runtime.launch(admission, runner=runner, user_safe_exceptions=user_safe_exceptions)
    if not isinstance(runtime.store, MemoryJobStore):
        raise APIError(503, "This caller must await start_job_async or prepare_job before accepting work.", error_code="async_job_admission_required")
    try:
        admitted = runtime.store.admit_sync(
            kind=kind, scope_id=scope_id, owner_id=user_id, input_data={},
            timeout_s=timeout_s, job_id_prefix=job_id_prefix,
        )
    except (AdmissionLimit, IdempotencyConflict) as exc:
        raise _admission_error(exc) from exc
    return runtime.launch(admitted, runner=runner, user_safe_exceptions=user_safe_exceptions)


async def get_job_async(app: Any, job_id: str, *, kind: str, scope_id: str, user_id: str) -> dict[str, Any] | None:
    store = job_runtime(app).store
    await store.recover(owner_id=user_id)
    return await store.get(job_id, kind=kind, scope_id=scope_id, owner_id=user_id)


def get_job(app: Any, job_id: str, *, kind: str, scope_id: str) -> Optional[dict[str, Any]]:
    store = job_runtime(app).store
    if not isinstance(store, MemoryJobStore):
        raise APIError(503, "This caller must await get_job_async with the verified owner.", error_code="async_job_admission_required")
    return store.get_sync(job_id, kind=kind, scope_id=scope_id)


async def running_jobs_for_user_async(app: Any, user_id: str) -> int:
    return await job_runtime(app).store.running_count(user_id)


def running_jobs_for_user(app: Any, user_id: Optional[str]) -> int:
    store = job_runtime(app).store
    if not isinstance(store, MemoryJobStore):
        raise APIError(503, "This caller must await durable job admission.", error_code="async_job_admission_required")
    return store.running_count_sync(user_id) if user_id else 0


async def startup_jobs(app: Any) -> list[dict[str, Any]]:
    return await job_runtime(app).startup()


async def initialize_jobs(app: Any) -> JobRuntime:
    runtime = job_runtime(app)
    await runtime.startup()
    return runtime


async def cancel_job_async(app: Any, job_id: str, *, kind: str, scope_id: str, user_id: str) -> dict[str, Any] | None:
    return await job_runtime(app).cancel(job_id, kind=kind, scope_id=scope_id, owner_id=user_id)


async def shutdown_jobs(app: Any) -> None:
    runtime = _state_get(app, "job_runtime")
    if runtime is not None:
        await runtime.shutdown()
