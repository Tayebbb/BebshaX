from __future__ import annotations

import asyncio
import hashlib
import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, overload

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.jobs.orm import DurableJobs, JobAttempts, JobCheckpoints, JobOwners

MAX_RUNNING_JOBS_PER_USER = 3
DEFAULT_JOB_TIMEOUT_S = 600.0
MAX_JOB_TIMEOUT_S = 3600.0
ACTIVE_STATES = ("queued", "running")
TERMINAL_STATES = ("completed", "failed", "cancelled", "interrupted", "timed_out")


class IdempotencyConflict(ValueError):
    pass


class AdmissionLimit(ValueError):
    pass


class LeaseLost(RuntimeError):
    pass


class UncertainItem(RuntimeError):
    pass


@dataclass(frozen=True)
class Lease:
    job_id: str
    owner_id: str
    token: str
    attempt: int
    deadline_at: datetime
    lease_s: float


@dataclass(frozen=True)
class Admission:
    job: dict[str, Any]
    created: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@overload
def aware(value: datetime) -> datetime: ...


@overload
def aware(value: None) -> None: ...


def aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def input_snapshot(value: Any) -> tuple[Any, str]:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValueError("Job input exceeds the 2 MiB journal limit; use immutable input references.")
    return json.loads(encoded), hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def bounded_timeout(timeout_s: float | None) -> float:
    duration = DEFAULT_JOB_TIMEOUT_S if timeout_s is None else timeout_s
    if (
        not isinstance(duration, (int, float)) or isinstance(duration, bool)
        or not math.isfinite(duration) or not 0 < duration <= MAX_JOB_TIMEOUT_S
    ):
        raise ValueError("Job timeout must be positive, finite, and at most 3600 seconds.")
    return float(duration)


def validated_revision(revision: str | None, digest: str) -> str:
    if revision is None:
        return digest
    if not isinstance(revision, str) or not revision.strip() or len(revision) > 255:
        raise ValueError("Input revision must contain between 1 and 255 characters.")
    return revision


def public_job(row: DurableJobs) -> dict[str, Any]:
    return {
        "job_id": row.id,
        "kind": row.kind,
        "scope_id": row.scope_id,
        "user_id": row.owner_id,
        "status": "running" if row.status in ACTIVE_STATES else "completed" if row.status == "completed" else "failed",
        "state": row.status,
        "result": row.result,
        "result_refs": row.result_refs,
        "error": row.error,
        "error_code": row.error_code,
        "started_at": aware(row.started_at).isoformat(),
        "finished_at": aware(row.finished_at).isoformat() if row.finished_at else None,
        "deadline_at": aware(row.deadline_at).isoformat(),
        "attempts": row.attempts,
        "input_hash": row.input_hash,
        "input_revision": row.input_revision,
        "payload_expired_at": aware(row.payload_expired_at).isoformat() if row.payload_expired_at else None,
    }


class SQLJobStore:
    def __init__(self, sessionmaker: Callable[[], AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def _lock_owner(self, session: AsyncSession, owner_id: str) -> None:
        dialect = session.get_bind().dialect.name
        insert = {"postgresql": pg_insert, "sqlite": sqlite_insert}.get(dialect)
        if insert is None:
            raise RuntimeError("The durable journal requires PostgreSQL (SQLite is supported for tests).")
        await session.execute(insert(JobOwners).values(owner_id=owner_id, revision=0).on_conflict_do_nothing())
        await session.execute(update(JobOwners).where(JobOwners.owner_id == owner_id).values(revision=JobOwners.revision + 1))

    async def admit(
        self, *, kind: str, scope_id: str, owner_id: str, input_data: dict[str, Any],
        idempotency_key: str | None = None, timeout_s: float | None = None,
        input_revision: str | None = None,
        worker_id: str | None = None,
        job_id_prefix: str = "job",
        prepare: Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ) -> Admission:
        for name, value, maximum in (
            ("owner_id", owner_id, 255), ("kind", kind, 64), ("scope_id", scope_id, 255),
            ("job_id_prefix", job_id_prefix, 32),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"{name} must contain between 1 and {maximum} characters.")
        if idempotency_key is not None and (
            not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200
        ):
            raise ValueError("Idempotency key must contain between 1 and 200 characters.")
        duration = bounded_timeout(timeout_s)
        if worker_id is not None and (not isinstance(worker_id, str) or not worker_id or len(worker_id) > 64):
            raise ValueError("Worker identity must contain between 1 and 64 characters.")
        snapshot, digest = input_snapshot(input_data)
        revision = validated_revision(input_revision, digest)
        key = idempotency_key or uuid.uuid4().hex
        await self.recover(owner_id=owner_id)
        async with self.sessionmaker() as session, session.begin():
            await self._lock_owner(session, owner_id)
            existing = await session.scalar(select(DurableJobs).where(
                DurableJobs.owner_id == owner_id, DurableJobs.idempotency_key == key,
            ))
            if existing is not None:
                if (existing.kind, existing.scope_id, existing.input_hash, existing.input_revision) != (
                    kind, scope_id, digest, revision,
                ):
                    raise IdempotencyConflict("This idempotency key was already used with different input.")
                admission = Admission(public_job(existing), False)
            else:
                count = await session.scalar(select(func.count()).select_from(DurableJobs).where(
                    DurableJobs.owner_id == owner_id, DurableJobs.status.in_(ACTIVE_STATES),
                ))
                if (count or 0) >= MAX_RUNNING_JOBS_PER_USER:
                    raise AdmissionLimit("You already have 3 background jobs running; wait for one to finish.")
                now = utcnow()
                row = DurableJobs(
                    id=f"{job_id_prefix}_{uuid.uuid4().hex[:24]}", owner_id=owner_id,
                    kind=kind, scope_id=scope_id, idempotency_key=key, input_hash=digest,
                    input_revision=revision, input_data=snapshot, status="queued", attempts=0, worker_id=worker_id,
                    started_at=now, deadline_at=now + timedelta(seconds=duration),
                    lease_expires_at=now + timedelta(seconds=60),
                )
                session.add(row)
                await session.flush()
                if prepare is not None:
                    row.result_refs = input_snapshot(await prepare(session, public_job(row)))[0]
                admission = Admission(public_job(row), True)
        return admission

    async def get(self, job_id: str, *, kind: str, scope_id: str, owner_id: str) -> dict[str, Any] | None:
        async with self.sessionmaker() as session:
            row = await session.scalar(select(DurableJobs).where(
                DurableJobs.id == job_id, DurableJobs.kind == kind,
                DurableJobs.scope_id == scope_id, DurableJobs.owner_id == owner_id,
            ))
            if row is None:
                return None
            checkpoints = (await session.scalars(select(JobCheckpoints).where(
                JobCheckpoints.job_id == job_id,
            ).order_by(JobCheckpoints.item_key))).all()
            result = public_job(row)
            result["checkpoints"] = [
                {"item_key": item.item_key, "state": item.status, "result_refs": item.result_refs}
                for item in checkpoints
            ]
            result["provider_outcome_unknown"] = any(item.status != "completed" for item in checkpoints)
            return result

    async def running_count(self, owner_id: str) -> int:
        await self.recover(owner_id=owner_id)
        async with self.sessionmaker() as session:
            return int(await session.scalar(select(func.count()).select_from(DurableJobs).where(
                DurableJobs.owner_id == owner_id, DurableJobs.status.in_(ACTIVE_STATES),
            )) or 0)

    async def cancel_queued(self, job_id: str, *, worker_id: str | None = None) -> None:
        async with self.sessionmaker() as session, session.begin():
            statement = select(DurableJobs).where(
                DurableJobs.id == job_id, DurableJobs.status == "queued",
            )
            if worker_id is not None:
                statement = statement.where(DurableJobs.worker_id == worker_id)
            row = await session.scalar(statement.with_for_update())
            if row is not None:
                await self._terminal(session, row, "cancelled", utcnow(), "cancelled (server shutting down)", "job_cancelled")

    async def _terminal(
        self, session: AsyncSession, row: DurableJobs, status: str, timestamp: datetime,
        error: str | None, error_code: str | None,
    ) -> None:
        row.status = status
        row.finished_at = timestamp
        row.lease_expires_at = None
        row.error = error
        row.error_code = error_code
        await session.execute(update(JobAttempts).where(
            JobAttempts.job_id == row.id, JobAttempts.status == "running",
        ).values(status=status, finished_at=timestamp))
        await session.execute(update(JobCheckpoints).where(
            JobCheckpoints.job_id == row.id, JobCheckpoints.status == "started",
        ).values(status="uncertain", updated_at=timestamp))

    async def cancel(self, job_id: str, *, kind: str, scope_id: str, owner_id: str) -> dict[str, Any] | None:
        async with self.sessionmaker() as session, session.begin():
            row = await session.scalar(select(DurableJobs).where(
                DurableJobs.id == job_id, DurableJobs.kind == kind,
                DurableJobs.scope_id == scope_id, DurableJobs.owner_id == owner_id,
            ).with_for_update())
            if row is None:
                return None
            if row.status in ACTIVE_STATES:
                await self._terminal(session, row, "cancelled", utcnow(), "Job cancelled.", "job_cancelled")
            return public_job(row)

    async def interrupt_worker(self, worker_id: str, *, job_id: str | None = None) -> list[dict[str, Any]]:
        interrupted: list[dict[str, Any]] = []
        async with self.sessionmaker() as session, session.begin():
            statement = select(DurableJobs).where(
                DurableJobs.worker_id == worker_id, DurableJobs.status.in_(ACTIVE_STATES),
            )
            if job_id is not None:
                statement = statement.where(DurableJobs.id == job_id)
            rows = (await session.scalars(statement.with_for_update())).all()
            for row in rows:
                state = "cancelled" if row.status == "queued" else "interrupted"
                await self._terminal(
                    session, row, state, utcnow(),
                    "Worker stopped; inspect saved results before explicitly retrying.", f"job_{state}",
                )
                interrupted.append(public_job(row))
        return interrupted

    async def claim(self, job_id: str, *, worker_id: str, lease_s: float = 60) -> Lease | None:
        if not worker_id or len(worker_id) > 64 or not math.isfinite(lease_s) or lease_s <= 0:
            raise ValueError("A worker identity and positive finite lease duration are required.")
        transaction = asyncio.create_task(self._claim(job_id, worker_id=worker_id, lease_s=lease_s))
        try:
            return await asyncio.shield(transaction)
        except asyncio.CancelledError:
            try:
                await transaction
            finally:
                raise

    async def _claim(self, job_id: str, *, worker_id: str, lease_s: float) -> Lease | None:
        now = utcnow()
        token = uuid.uuid4().hex
        async with self.sessionmaker() as session, session.begin():
            row = await session.scalar(update(DurableJobs).where(
                DurableJobs.id == job_id, DurableJobs.status == "queued",
                or_(DurableJobs.worker_id.is_(None), DurableJobs.worker_id == worker_id),
                DurableJobs.deadline_at > now, DurableJobs.lease_expires_at > now,
            ).values(
                status="running", worker_id=worker_id, lease_token=token,
                lease_expires_at=now + timedelta(seconds=lease_s), attempts=DurableJobs.attempts + 1,
            ).returning(DurableJobs))
            if row is None:
                return None
            session.add(JobAttempts(
                job_id=job_id, number=row.attempts, worker_id=worker_id, lease_token=token,
                status="running", started_at=now,
            ))
            lease = Lease(job_id, row.owner_id, token, row.attempts, aware(row.deadline_at), lease_s)
        return lease

    async def fence(self, session: AsyncSession, lease: Lease, *, require_deadline: bool = True) -> None:
        now = utcnow()
        statement = update(DurableJobs).where(
            DurableJobs.id == lease.job_id, DurableJobs.owner_id == lease.owner_id,
            DurableJobs.status == "running", DurableJobs.lease_token == lease.token,
            DurableJobs.attempts == lease.attempt,
            DurableJobs.lease_expires_at > now,
        )
        if require_deadline:
            statement = statement.where(DurableJobs.deadline_at > now)
        changed = await session.scalar(statement.values(lease_token=lease.token).returning(DurableJobs.id))
        if changed is None:
            raise LeaseLost("Job lease is no longer current; this worker cannot persist results.")

    async def heartbeat(self, lease: Lease) -> None:
        async with self.sessionmaker() as session, session.begin():
            await self.fence(session, lease)
            await session.execute(update(DurableJobs).where(DurableJobs.id == lease.job_id).values(
                lease_expires_at=utcnow() + timedelta(seconds=lease.lease_s),
            ))

    async def finish(
        self, lease: Lease, *, status: str = "completed", result: Any = None,
        result_refs: dict[str, Any] | None = None, error: str | None = None, error_code: str | None = None,
    ) -> None:
        if status not in TERMINAL_STATES:
            raise ValueError("Invalid terminal job state.")
        snapshot = input_snapshot(result)[0]
        refs = input_snapshot(result_refs)[0]
        async with self.sessionmaker() as session, session.begin():
            await self.fence(session, lease, require_deadline=status == "completed")
            row = await session.get(DurableJobs, lease.job_id)
            if row is None:
                raise LeaseLost("Job no longer exists.")
            if status == "completed":
                unfinished = await session.scalar(select(func.count()).select_from(JobCheckpoints).where(
                    JobCheckpoints.job_id == lease.job_id, JobCheckpoints.status != "completed",
                ))
                if unfinished:
                    status, snapshot = "interrupted", None
                    error = "A provider attempt has no committed checkpoint; inspect saved results before explicitly retrying."
                    error_code = "job_outcome_uncertain"
            row.result = snapshot
            if refs is not None:
                row.result_refs = refs
            await self._terminal(session, row, status, utcnow(), error, error_code)

    async def recover(self, *, owner_id: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
        timestamp = now or utcnow()
        statement = select(DurableJobs).where(
            DurableJobs.status.in_(ACTIVE_STATES),
            or_(DurableJobs.deadline_at <= timestamp, DurableJobs.lease_expires_at <= timestamp, DurableJobs.lease_expires_at.is_(None)),
        )
        if owner_id is not None:
            statement = statement.where(DurableJobs.owner_id == owner_id)
        recovered: list[dict[str, Any]] = []
        async with self.sessionmaker() as session, session.begin():
            rows = (await session.scalars(statement.with_for_update(skip_locked=True))).all()
            for row in rows:
                changed = await session.scalar(update(DurableJobs).where(
                    DurableJobs.id == row.id, DurableJobs.status.in_(ACTIVE_STATES),
                    or_(DurableJobs.deadline_at <= timestamp, DurableJobs.lease_expires_at <= timestamp, DurableJobs.lease_expires_at.is_(None)),
                ).values(status="interrupted", finished_at=timestamp).returning(DurableJobs.id).execution_options(synchronize_session=False))
                if changed is None:
                    continue
                timed_out = aware(row.deadline_at) <= timestamp
                await self._terminal(
                    session, row, "timed_out" if timed_out else "interrupted", timestamp,
                    "The background job exceeded its time limit." if timed_out else "Worker interrupted; review saved results before explicitly retrying.",
                    "job_timeout" if timed_out else "job_interrupted",
                )
                recovered.append(public_job(row))
        return recovered

    async def compact_terminal(self, *, before: datetime, limit: int = 100) -> int:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ValueError("Retention batches must contain between 1 and 1000 jobs.")
        async with self.sessionmaker() as session, session.begin():
            rows = (await session.scalars(select(DurableJobs).where(
                DurableJobs.status.in_(TERMINAL_STATES), DurableJobs.finished_at < aware(before),
                DurableJobs.payload_expired_at.is_(None),
            ).order_by(DurableJobs.finished_at).limit(limit).with_for_update(skip_locked=True))).all()
            for row in rows:
                row.input_data = {}
                row.result = None
                row.payload_expired_at = utcnow()
                await session.execute(update(JobCheckpoints).where(
                    JobCheckpoints.job_id == row.id,
                ).values(input_data={}))
            return len(rows)

    async def begin_item(self, lease: Lease, item_key: str, *, input_data: dict[str, Any]) -> dict[str, Any]:
        if not item_key or len(item_key) > 255:
            raise ValueError("Item key must contain between 1 and 255 characters.")
        snapshot, digest = input_snapshot(input_data)
        async with self.sessionmaker() as session, session.begin():
            await self.fence(session, lease)
            row = await session.get(JobCheckpoints, (lease.job_id, item_key))
            if row is not None:
                if row.input_hash != digest:
                    raise IdempotencyConflict("Checkpoint input changed.")
                if row.status != "completed":
                    raise UncertainItem("This item may already have called an external service; automatic replay is forbidden.")
                return {"status": row.status, "result_refs": row.result_refs}
            session.add(JobCheckpoints(
                job_id=lease.job_id, item_key=item_key, input_hash=digest, input_data=snapshot, status="started",
                result_refs=None, lease_token=lease.token, updated_at=utcnow(),
            ))
        return {"status": "started", "result_refs": None}

    async def complete_item(
        self, lease: Lease, item_key: str, *, result_refs: dict[str, Any], session: AsyncSession | None = None,
    ) -> None:
        if session is None:
            async with self.sessionmaker() as own_session, own_session.begin():
                await self.complete_item(lease, item_key, result_refs=result_refs, session=own_session)
            return
        snapshot = input_snapshot(result_refs)[0]
        await self.fence(session, lease)
        row = await session.get(JobCheckpoints, (lease.job_id, item_key))
        if row is None or row.lease_token != lease.token:
            raise LeaseLost("Checkpoint is not owned by this attempt.")
        if row.status == "completed" and row.result_refs != snapshot:
            raise IdempotencyConflict("Completed checkpoint references are immutable.")
        row.status = "completed"
        row.result_refs = snapshot
        row.updated_at = utcnow()