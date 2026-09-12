from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta
from typing import Any

from bebshax.jobs.orm import DurableJobs
from bebshax.jobs.store import (
    ACTIVE_STATES, MAX_RUNNING_JOBS_PER_USER, TERMINAL_STATES, Admission, AdmissionLimit,
    IdempotencyConflict, Lease, LeaseLost, UncertainItem, bounded_timeout, input_snapshot, public_job, utcnow,
    validated_revision,
)


class MemoryJobStore:
    """Explicitly injected test double. Never selected by configuration fallback."""

    def __init__(self) -> None:
        self.rows: dict[str, DurableJobs] = {}
        self.checkpoints: dict[tuple[str, str], dict[str, Any]] = {}

    def admit_sync(
        self, *, kind: str, scope_id: str, owner_id: str, input_data: dict[str, Any],
        idempotency_key: str | None = None, timeout_s: float | None = None,
        input_revision: str | None = None,
        worker_id: str | None = None,
        job_id_prefix: str = "job", prepare: Any = None,
    ) -> Admission:
        if prepare is not None:
            raise ValueError("Transactional preparation requires SQLJobStore.")
        if not owner_id:
            raise ValueError("owner_id is required.")
        duration = bounded_timeout(timeout_s)
        snapshot, digest = input_snapshot(input_data)
        revision = validated_revision(input_revision, digest)
        key = idempotency_key or uuid.uuid4().hex
        for row in self.rows.values():
            if (row.owner_id, row.idempotency_key) == (owner_id, key):
                if (row.kind, row.scope_id, row.input_hash, row.input_revision) != (kind, scope_id, digest, revision):
                    raise IdempotencyConflict("This idempotency key was already used with different input.")
                return Admission(copy.deepcopy(public_job(row)), False)
        if self.running_count_sync(owner_id) >= MAX_RUNNING_JOBS_PER_USER:
            raise AdmissionLimit("You already have 3 background jobs running; wait for one to finish.")
        now = utcnow()
        row = DurableJobs(
            id=f"{job_id_prefix}_{uuid.uuid4().hex[:24]}", owner_id=owner_id, kind=kind,
            scope_id=scope_id, input_revision=revision, input_data=snapshot, input_hash=digest, idempotency_key=key,
            status="queued", attempts=0, started_at=now, worker_id=worker_id,
            deadline_at=now + timedelta(seconds=duration),
            lease_expires_at=now + timedelta(seconds=60),
        )
        self.rows[row.id] = row
        return Admission(public_job(row), True)

    async def admit(self, **kwargs: Any) -> Admission:
        await self.recover(owner_id=kwargs.get("owner_id"))
        return self.admit_sync(**kwargs)

    def running_count_sync(self, owner_id: str) -> int:
        return sum(row.owner_id == owner_id and row.status in ACTIVE_STATES for row in self.rows.values())

    async def running_count(self, owner_id: str) -> int:
        await self.recover(owner_id=owner_id)
        return self.running_count_sync(owner_id)

    def get_sync(self, job_id: str, *, kind: str, scope_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        row = self.rows.get(job_id)
        if row is None or row.kind != kind or row.scope_id != scope_id or (owner_id is not None and row.owner_id != owner_id):
            return None
        result = copy.deepcopy(public_job(row))
        result["checkpoints"] = [
            {"item_key": item_key, "state": item["status"], "result_refs": copy.deepcopy(item["result_refs"])}
            for (checkpoint_job_id, item_key), item in sorted(self.checkpoints.items()) if checkpoint_job_id == job_id
        ]
        result["provider_outcome_unknown"] = any(item["state"] != "completed" for item in result["checkpoints"])
        return result

    async def get(self, job_id: str, *, kind: str, scope_id: str, owner_id: str) -> dict[str, Any] | None:
        return self.get_sync(job_id, kind=kind, scope_id=scope_id, owner_id=owner_id)

    async def claim(self, job_id: str, *, worker_id: str, lease_s: float = 60) -> Lease | None:
        row = self.rows.get(job_id)
        if row is None or row.status != "queued" or row.deadline_at <= utcnow() or row.worker_id not in (None, worker_id):
            return None
        if row.lease_expires_at is None or row.lease_expires_at <= utcnow():
            return None
        row.status = "running"
        row.worker_id = worker_id
        token = uuid.uuid4().hex
        row.lease_token = token
        row.attempts += 1
        row.lease_expires_at = utcnow() + timedelta(seconds=lease_s)
        return Lease(row.id, row.owner_id, token, row.attempts, row.deadline_at, lease_s)

    async def fence(self, session: Any, lease: Lease, *, require_deadline: bool = True) -> None:
        row = self.rows.get(lease.job_id)
        if (
            row is None or row.status != "running" or row.lease_token != lease.token
            or row.owner_id != lease.owner_id or row.attempts != lease.attempt
            or row.lease_expires_at is None or row.lease_expires_at <= utcnow()
        ):
            raise LeaseLost("Job lease is no longer current.")
        if require_deadline and row.deadline_at <= utcnow():
            raise LeaseLost("Job deadline exceeded.")

    async def heartbeat(self, lease: Lease) -> None:
        await self.fence(None, lease)
        self.rows[lease.job_id].lease_expires_at = utcnow() + timedelta(seconds=lease.lease_s)

    async def finish(self, lease: Lease, *, status: str = "completed", result: Any = None,
                     result_refs: dict[str, Any] | None = None, error: str | None = None,
                     error_code: str | None = None) -> None:
        if status not in TERMINAL_STATES:
            raise ValueError("Invalid terminal job state.")
        snapshot = input_snapshot(result)[0]
        refs = input_snapshot(result_refs)[0]
        await self.fence(None, lease, require_deadline=status == "completed")
        row = self.rows[lease.job_id]
        if status == "completed" and any(
            job_id == lease.job_id and item["status"] != "completed"
            for (job_id, item_key), item in self.checkpoints.items()
        ):
            status, snapshot = "interrupted", None
            error = "A provider attempt has no committed checkpoint; inspect saved results before explicitly retrying."
            error_code = "job_outcome_uncertain"
        row.result = snapshot
        if refs is not None:
            row.result_refs = refs
        self._terminal(row, status, utcnow(), error, error_code)

    def _terminal(self, row: DurableJobs, status: str, timestamp: datetime, error: str | None, error_code: str | None) -> None:
        row.status = status
        row.error = error
        row.error_code = error_code
        row.finished_at = timestamp
        row.lease_expires_at = None
        for (job_id, item_key), item in self.checkpoints.items():
            if job_id == row.id and item["status"] == "started":
                item["status"] = "uncertain"

    async def recover(self, *, owner_id: str | None = None, now: datetime | None = None) -> list[dict[str, Any]]:
        timestamp = now or utcnow()
        recovered = []
        for row in self.rows.values():
            if (owner_id is None or row.owner_id == owner_id) and row.status in ACTIVE_STATES and (
                row.deadline_at <= timestamp or row.lease_expires_at is None or row.lease_expires_at <= timestamp
            ):
                timed_out = row.deadline_at <= timestamp
                self._terminal(
                    row, "timed_out" if timed_out else "interrupted", timestamp,
                    "The background job exceeded its time limit." if timed_out else "Worker interrupted; review saved results before explicitly retrying.",
                    "job_timeout" if timed_out else "job_interrupted",
                )
                recovered.append(public_job(row))
        return recovered

    async def cancel_queued(self, job_id: str, *, worker_id: str | None = None) -> None:
        row = self.rows.get(job_id)
        if row and row.status == "queued" and (worker_id is None or row.worker_id == worker_id):
            self._terminal(row, "cancelled", utcnow(), "cancelled (server shutting down)", "job_cancelled")

    async def interrupt_worker(self, worker_id: str, *, job_id: str | None = None) -> list[dict[str, Any]]:
        interrupted = []
        for row in self.rows.values():
            if row.worker_id == worker_id and row.status in ACTIVE_STATES and (job_id is None or row.id == job_id):
                state = "cancelled" if row.status == "queued" else "interrupted"
                self._terminal(row, state, utcnow(), "Worker stopped; inspect saved results before explicitly retrying.", f"job_{state}")
                interrupted.append(copy.deepcopy(public_job(row)))
        return interrupted

    async def cancel(self, job_id: str, *, kind: str, scope_id: str, owner_id: str) -> dict[str, Any] | None:
        if self.get_sync(job_id, kind=kind, scope_id=scope_id, owner_id=owner_id) is None:
            return None
        row = self.rows[job_id]
        if row.status in ACTIVE_STATES:
            self._terminal(row, "cancelled", utcnow(), "Job cancelled.", "job_cancelled")
        return copy.deepcopy(public_job(row))

    async def begin_item(self, lease: Lease, item_key: str, *, input_data: dict[str, Any]) -> dict[str, Any]:
        if not item_key or len(item_key) > 255:
            raise ValueError("Item key must contain between 1 and 255 characters.")
        snapshot, digest = input_snapshot(input_data)
        await self.fence(None, lease)
        key = (lease.job_id, item_key)
        item = self.checkpoints.get(key)
        if item is not None:
            if item["input_hash"] != digest:
                raise IdempotencyConflict("Checkpoint input changed.")
            if item["status"] != "completed":
                raise UncertainItem("This item may already have called an external service; automatic replay is forbidden.")
            return {"status": "completed", "result_refs": copy.deepcopy(item["result_refs"])}
        self.checkpoints[key] = {
            "status": "started", "input_hash": digest, "input_data": snapshot,
            "result_refs": None, "lease_token": lease.token,
        }
        return {"status": "started", "result_refs": None}

    async def complete_item(self, lease: Lease, item_key: str, *, result_refs: dict[str, Any], session: Any = None) -> None:
        snapshot = input_snapshot(result_refs)[0]
        await self.fence(session, lease)
        item = self.checkpoints.get((lease.job_id, item_key))
        if item is None or item["lease_token"] != lease.token:
            raise LeaseLost("Checkpoint is not owned by this attempt.")
        if item["status"] == "completed" and item["result_refs"] != snapshot:
            raise IdempotencyConflict("Completed checkpoint references are immutable.")
        item["status"] = "completed"
        item["result_refs"] = snapshot