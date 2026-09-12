from datetime import timedelta

import pytest
from sqlalchemy import select

from bebshax.jobs.orm import JobAttempts
from bebshax.jobs.store import LeaseLost, SQLJobStore, UncertainItem, utcnow


async def test_cancellation_is_owner_scoped_durable_and_fences_results(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    job_id = admitted.job["job_id"]
    lease = await job_store.claim(job_id, worker_id="worker-1")
    await job_store.begin_item(lease, "external-call", input_data={"revision": 1})
    other_instance = SQLJobStore(job_store.sessionmaker)
    assert await other_instance.cancel(job_id, kind="research", scope_id="study-1", owner_id="owner-2") is None
    assert await other_instance.cancel(job_id, kind="report", scope_id="study-1", owner_id="owner-1") is None
    cancelled = await other_instance.cancel(job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert cancelled["state"] == "cancelled"
    saved = await job_store.get(job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert saved["checkpoints"][0]["state"] == "uncertain"
    assert saved["provider_outcome_unknown"] is True
    with pytest.raises(LeaseLost):
        await job_store.finish(lease, result={"late": True})
    with pytest.raises(LeaseLost):
        await job_store.complete_item(lease, "external-call", result_refs={"result_id": "late"})
    async with job_store.sessionmaker() as session:
        attempt = await session.scalar(select(JobAttempts).where(JobAttempts.job_id == job_id))
        assert attempt.status == "cancelled"


async def test_restart_preserves_checkpoints_without_replaying_unknown_calls(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    job_id = admitted.job["job_id"]
    lease = await job_store.claim(job_id, worker_id="dead-worker", lease_s=1)
    await job_store.begin_item(lease, "saved", input_data={"revision": 1})
    await job_store.complete_item(lease, "saved", result_refs={"report_id": "report-1"})
    cached = await job_store.begin_item(lease, "saved", input_data={"revision": 1})
    assert cached["status"] == "completed"
    await job_store.begin_item(lease, "unknown", input_data={"revision": 2})
    with pytest.raises(UncertainItem):
        await job_store.begin_item(lease, "unknown", input_data={"revision": 2})
    restarted_store = SQLJobStore(job_store.sessionmaker)
    recovered = await restarted_store.recover(now=utcnow() + timedelta(seconds=2))
    assert [job["job_id"] for job in recovered] == [job_id]
    assert recovered[0]["state"] == "interrupted"
    assert await restarted_store.claim(job_id, worker_id="new-worker") is None
    saved = await restarted_store.get(job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    checkpoints = {item["item_key"]: item for item in saved["checkpoints"]}
    assert checkpoints["saved"]["result_refs"] == {"report_id": "report-1"}
    assert checkpoints["unknown"]["state"] == "uncertain"
    assert all("input_data" not in item and "lease_token" not in item for item in saved["checkpoints"])


async def test_recovery_persists_a_distinct_timeout_state(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(
        kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, timeout_s=1,
    )
    lease = await job_store.claim(admitted.job["job_id"], worker_id="worker-1")
    recovered = await job_store.recover(now=utcnow() + timedelta(seconds=2))
    assert recovered[0]["state"] == "timed_out"
    assert recovered[0]["error_code"] == "job_timeout"
    async with job_store.sessionmaker() as session:
        attempt = await session.get(JobAttempts, (lease.job_id, lease.attempt))
        assert attempt.status == "timed_out"


async def test_retention_preserves_live_jobs_and_command_tombstones(job_store: SQLJobStore) -> None:
    command = dict(kind="report", scope_id="study-1", owner_id="owner-1", input_data={"revision": 1}, idempotency_key="saved")
    completed = await job_store.admit(**command)
    lease = await job_store.claim(completed.job["job_id"], worker_id="worker-1")
    await job_store.finish(lease, result={"large": "payload"}, result_refs={"report_id": "report-1"})
    active = await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={"live": True})
    assert await job_store.compact_terminal(before=utcnow()) == 1
    duplicate = await job_store.admit(**command)
    assert not duplicate.created
    assert duplicate.job["job_id"] == completed.job["job_id"]
    assert duplicate.job["result"] is None
    assert duplicate.job["payload_expired_at"] is not None
    assert duplicate.job["result_refs"] == {"report_id": "report-1"}
    live = await job_store.get(active.job["job_id"], kind="research", scope_id="study-1", owner_id="owner-1")
    assert live["state"] == "queued"
    assert live["payload_expired_at"] is None


async def test_incomplete_provider_checkpoint_cannot_be_reported_completed(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    lease = await job_store.claim(admitted.job["job_id"], worker_id="worker-1")
    await job_store.begin_item(lease, "provider-call", input_data={"revision": 1})
    await job_store.finish(lease, result={"unsupported_success": True})
    saved = await job_store.get(lease.job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert saved["state"] == "interrupted"
    assert saved["error_code"] == "job_outcome_uncertain"
    assert saved["result"] is None


async def test_checkpoint_joins_caller_transaction_and_rolls_back(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    lease = await job_store.claim(admitted.job["job_id"], worker_id="worker-1")
    await job_store.begin_item(lease, "provider-call", input_data={"revision": 1})
    with pytest.raises(RuntimeError, match="Rollback artifact"):
        async with job_store.sessionmaker() as session, session.begin():
            await job_store.complete_item(lease, "provider-call", result_refs={"report_id": "rolled-back"}, session=session)
            raise RuntimeError("Rollback artifact")
    with pytest.raises(UncertainItem):
        await job_store.begin_item(lease, "provider-call", input_data={"revision": 1})
    saved = await job_store.get(lease.job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert saved["checkpoints"][0]["result_refs"] is None