from __future__ import annotations

import asyncio
import logging
import math
import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.jobs.memory import MemoryJobStore
from bebshax.jobs.store import Admission, Lease, LeaseLost, SQLJobStore, utcnow
from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)
Runner = Callable[["JobContext"], Awaitable[None]]
Prepare = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]


class RuntimeClosing(RuntimeError):
    pass


class FencedSession:
    """Delegate session operations while requiring a current job lease at commit."""

    def __init__(
        self, session: AsyncSession, job: JobContext,
        before_commit: Callable[[AsyncSession], Awaitable[None]] | None = None,
    ) -> None:
        self.session = session
        self.job = job
        self.before_commit = before_commit

    def __getattr__(self, name: str) -> Any:
        return getattr(self.session, name)

    async def commit(self) -> None:
        await self.job.fence(self.session)
        if self.before_commit is not None:
            await self.before_commit(self.session)
        await self.session.commit()


class JobContext(dict[str, Any]):
    def __init__(self, job: dict[str, Any], store: SQLJobStore | MemoryJobStore, lease: Lease) -> None:
        super().__init__(job)
        self.store = store
        self.lease = lease

    async def fence(self, session: AsyncSession) -> None:
        await self.store.fence(session, self.lease)

    async def begin_item(self, item_key: str, *, input_data: dict[str, Any]) -> dict[str, Any]:
        return await self.store.begin_item(self.lease, item_key, input_data=input_data)

    async def complete_item(self, item_key: str, *, result_refs: dict[str, Any], session: AsyncSession | None = None) -> None:
        await self.store.complete_item(self.lease, item_key, result_refs=result_refs, session=session)


class JobRuntime:
    def __init__(
        self, store: SQLJobStore | MemoryJobStore, *, lease_s: float = 60,
        register_task: Callable[[asyncio.Task[None]], Any] | None = None,
    ) -> None:
        if not math.isfinite(lease_s) or not 0 < lease_s <= 300:
            raise ValueError("Lease duration must be positive, finite, and at most 300 seconds.")
        self.store = store
        self.lease_s = lease_s
        self.register_task = register_task
        self.worker_id = uuid.uuid4().hex
        self.tasks: set[asyncio.Task[None]] = set()
        self._job_ids: set[str] = set()
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._recovery_task: asyncio.Task[None] | None = None
        self._closing = False

    async def startup(self) -> list[dict[str, Any]]:
        if self._closing:
            raise RuntimeClosing("Job runtime is shutting down.")
        recovered = await self.store.recover()
        if self._closing:
            raise RuntimeClosing("Job runtime is shutting down.")
        if self._recovery_task is None or self._recovery_task.done():
            self._recovery_task = asyncio.create_task(self._recover_expired())
            if self.register_task is not None:
                try:
                    self.register_task(self._recovery_task)
                except Exception:
                    self._recovery_task.cancel()
                    raise
        return recovered

    async def _recover_expired(self) -> None:
        while True:
            await asyncio.sleep(self.lease_s / 3)
            try:
                await self.store.recover()
            except Exception as exc:
                logger.warning("Job recovery unavailable (%s)", type(exc).__name__)

    async def prepare(
        self, *, kind: str, scope_id: str, owner_id: str, input_data: dict[str, Any],
        idempotency_key: str | None = None, timeout_s: float | None = None,
        input_revision: str | None = None, job_id_prefix: str = "job", prepare: Prepare | None = None,
    ) -> Admission:
        if self._closing:
            raise RuntimeClosing("Job runtime is shutting down.")
        admission = await self.store.admit(
            kind=kind, scope_id=scope_id, owner_id=owner_id, input_data=input_data,
            idempotency_key=idempotency_key, timeout_s=timeout_s, input_revision=input_revision,
            job_id_prefix=job_id_prefix, prepare=prepare, worker_id=self.worker_id,
        )
        if self._closing:
            if admission.created:
                await self.store.cancel_queued(admission.job["job_id"], worker_id=self.worker_id)
            raise RuntimeClosing("Job runtime is shutting down.")
        return admission

    async def start(
        self, *, kind: str, scope_id: str, owner_id: str, input_data: dict[str, Any], runner: Runner,
        idempotency_key: str | None = None, timeout_s: float | None = None,
        input_revision: str | None = None,
        job_id_prefix: str = "job", user_safe_exceptions: tuple[type[BaseException], ...] = (),
        prepare: Prepare | None = None,
    ) -> dict[str, Any]:
        admission = await self.prepare(
            kind=kind, scope_id=scope_id, owner_id=owner_id, input_data=input_data,
            idempotency_key=idempotency_key, timeout_s=timeout_s, job_id_prefix=job_id_prefix, prepare=prepare,
            input_revision=input_revision,
        )
        try:
            return self.launch(admission, runner=runner, user_safe_exceptions=user_safe_exceptions)
        except Exception:
            if admission.created:
                await self.store.cancel_queued(admission.job["job_id"], worker_id=self.worker_id)
            raise

    def launch(self, admission: Admission, *, runner: Runner,
               user_safe_exceptions: tuple[type[BaseException], ...] = ()) -> dict[str, Any]:
        if self._closing:
            raise RuntimeClosing("Job runtime is shutting down.")
        if not admission.created:
            return admission.job
        job_id = admission.job["job_id"]
        if job_id in self._job_tasks:
            return admission.job
        self._job_ids.add(job_id)
        task = asyncio.create_task(self._execute(admission.job, runner, user_safe_exceptions))
        self.tasks.add(task)
        self._job_tasks[job_id] = task

        def done(completed: asyncio.Task[None]) -> None:
            self.tasks.discard(completed)
            self._job_ids.discard(job_id)
            self._job_tasks.pop(job_id, None)
            if not completed.cancelled() and completed.exception() is not None:
                logger.error("Job %s could not persist terminal state (%s)", job_id, type(completed.exception()).__name__)

        task.add_done_callback(done)
        if self.register_task is not None:
            try:
                self.register_task(task)
            except Exception:
                task.cancel()
                raise
        return admission.job

    async def _heartbeat(self, lease: Lease, stopped: asyncio.Event, worker: asyncio.Task[Any], interrupted: asyncio.Event) -> None:
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=self.lease_s / 3)
            except TimeoutError:
                if stopped.is_set():
                    return
                try:
                    await self.store.heartbeat(lease)
                except Exception:
                    interrupted.set()
                    worker.cancel()
                    return

    async def _execute(self, job: dict[str, Any], runner: Runner,
                       user_safe_exceptions: tuple[type[BaseException], ...]) -> None:
        try:
            await self._run(job, runner, user_safe_exceptions)
        finally:
            cleanup = asyncio.create_task(self.store.interrupt_worker(self.worker_id, job_id=job["job_id"]))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup

    async def _run(self, job: dict[str, Any], runner: Runner,
                   user_safe_exceptions: tuple[type[BaseException], ...]) -> None:
        lease = await self.store.claim(job["job_id"], worker_id=self.worker_id, lease_s=self.lease_s)
        if lease is None:
            await self.store.recover()
            return
        context = JobContext(job, self.store, lease)
        stopped = asyncio.Event()
        interrupted = asyncio.Event()
        worker = asyncio.current_task()
        if worker is None:
            raise RuntimeError("Job execution requires an asyncio task.")
        heartbeat = asyncio.create_task(self._heartbeat(lease, stopped, worker, interrupted))
        state = "completed"
        error = error_code = None
        try:
            remaining = max(0.0, (lease.deadline_at - utcnow()).total_seconds())
            async with asyncio.timeout(remaining):
                await runner(context)
            if utcnow() >= lease.deadline_at:
                raise TimeoutError
            if interrupted.is_set() or self._closing or worker.cancelling():
                raise asyncio.CancelledError
        except TimeoutError:
            state, error, error_code = "timed_out", "The background job exceeded its time limit.", "job_timeout"
        except asyncio.CancelledError:
            if utcnow() >= lease.deadline_at:
                state, error, error_code = "timed_out", "The background job exceeded its time limit.", "job_timeout"
            elif interrupted.is_set():
                state, error, error_code = "interrupted", "Worker lease could not be maintained; inspect saved results before retrying.", "job_interrupted"
            else:
                state, error, error_code = "cancelled", "cancelled (server shutting down)", "job_cancelled"
        except ExplicitFailure as exc:
            state, error, error_code = "failed", exc.detail, exc.error_code
        except (ValueError, *user_safe_exceptions) as exc:
            state, error = "failed", str(exc)
        except Exception as exc:
            state, error = "failed", f"{type(exc).__name__}: {job['kind']} failed"
        finally:
            stopped.set()
            finishing = asyncio.create_task(self._finalize(context, state, error, error_code, heartbeat))
            try:
                await asyncio.shield(finishing)
            except asyncio.CancelledError:
                await finishing

    async def _finalize(self, context: JobContext, state: str, error: str | None,
                        error_code: str | None, heartbeat: asyncio.Task[None]) -> None:
        await heartbeat
        try:
            try:
                await self.store.finish(
                    context.lease, status=state,
                    result=context.get("result") if state == "completed" else None,
                    result_refs=context.get("result_refs"),
                    error=error, error_code=error_code,
                )
            except (ValueError, TypeError):
                await self.store.finish(
                    context.lease, status="failed", result=None,
                    error="The job result could not be recorded; inspect persisted artifact references.",
                    error_code="job_result_invalid",
                )
        except LeaseLost:
            await self.store.recover(owner_id=context.lease.owner_id)

    async def drain(self) -> None:
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)

    async def wait(self, job_id: str) -> None:
        task = self._job_tasks.get(job_id)
        if task is not None:
            await asyncio.shield(task)

    async def cancel(self, job_id: str, *, kind: str, scope_id: str, owner_id: str) -> dict[str, Any] | None:
        await self.store.recover(owner_id=owner_id)
        result = await self.store.cancel(job_id, kind=kind, scope_id=scope_id, owner_id=owner_id)
        if result is not None and result["state"] == "cancelled":
            task = self._job_tasks.get(job_id)
            if task is not None:
                task.cancel()
        return result

    async def shutdown(self, *, timeout_s: float = 10) -> None:
        if not math.isfinite(timeout_s) or not 0 < timeout_s <= 60:
            raise ValueError("Shutdown timeout must be positive, finite, and at most 60 seconds.")
        self._closing = True
        tasks = set(self.tasks)
        if self._recovery_task is not None:
            tasks.add(self._recovery_task)
        for task in tasks:
            task.cancel()
        pending = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout_s)
        await self.store.interrupt_worker(self.worker_id)
        if pending:
            raise RuntimeError("Job workers did not stop before shutdown; shared resources must remain open.")

    async def aclose(self) -> None:
        await self.shutdown()