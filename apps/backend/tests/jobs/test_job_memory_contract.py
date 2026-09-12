from types import SimpleNamespace

import pytest

from bebshax.api.errors import APIError
from bebshax.api.jobs import job_runtime
from bebshax.jobs.memory import MemoryJobStore
from bebshax.jobs.store import LeaseLost, UncertainItem


async def test_memory_double_exposes_checkpoints_and_fenced_cancellation() -> None:
    store = MemoryJobStore()
    admitted = await store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    lease = await store.claim(admitted.job["job_id"], worker_id="worker-1")
    await store.begin_item(lease, "saved", input_data={"revision": 1})
    await store.complete_item(lease, "saved", result_refs={"result_id": "saved"})
    await store.begin_item(lease, "unknown", input_data={"revision": 2})
    with pytest.raises(UncertainItem):
        await store.begin_item(lease, "unknown", input_data={"revision": 2})
    cancelled = await store.cancel(lease.job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert cancelled["state"] == "cancelled"
    with pytest.raises(LeaseLost):
        await store.finish(lease)
    saved = await store.get(lease.job_id, kind="research", scope_id="study-1", owner_id="owner-1")
    assert [item["state"] for item in saved["checkpoints"]] == ["completed", "uncertain"]
    assert saved["provider_outcome_unknown"] is True


def test_legacy_app_jobs_never_becomes_implicit_storage() -> None:
    app = SimpleNamespace(state=SimpleNamespace(jobs={"legacy": {"status": "running"}}))
    with pytest.raises(APIError) as unavailable:
        job_runtime(app)
    assert unavailable.value.status_code == 503
    assert app.state.jobs == {"legacy": {"status": "running"}}