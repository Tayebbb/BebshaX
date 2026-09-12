from datetime import datetime

import pytest

from bebshax.jobs.store import AdmissionLimit, IdempotencyConflict, SQLJobStore


async def test_default_deadline_is_ten_minutes(job_store: SQLJobStore) -> None:
    admitted = await job_store.admit(
        kind="research", scope_id="study-1", owner_id="owner-1", input_data={"revision": 1},
    )
    job = admitted.job
    duration = datetime.fromisoformat(job["deadline_at"]) - datetime.fromisoformat(job["started_at"])
    assert duration.total_seconds() == 600


@pytest.mark.parametrize("kind,scope_id", [("report", "study-1"), ("research", "study-2")])
async def test_owner_key_cannot_identify_another_command(
    job_store: SQLJobStore, kind: str, scope_id: str,
) -> None:
    await job_store.admit(
        kind="research", scope_id="study-1", owner_id="owner-1", input_data={"revision": 1},
        idempotency_key="command-1",
    )
    other_instance = SQLJobStore(job_store.sessionmaker)
    with pytest.raises(IdempotencyConflict):
        await other_instance.admit(
            kind=kind, scope_id=scope_id, owner_id="owner-1", input_data={"revision": 1},
            idempotency_key="command-1",
        )


async def test_exact_revision_is_part_of_idempotency_contract(job_store: SQLJobStore) -> None:
    command = dict(
        kind="research", scope_id="study-1", owner_id="owner-1",
        input_data={"question": "A synthetic question"}, idempotency_key="revision-command",
    )
    original = await job_store.admit(**command, input_revision="study:4")
    duplicate = await SQLJobStore(job_store.sessionmaker).admit(**command, input_revision="study:4")
    assert not duplicate.created
    assert duplicate.job["job_id"] == original.job["job_id"]
    assert duplicate.job["input_revision"] == "study:4"
    with pytest.raises(IdempotencyConflict):
        await job_store.admit(**command, input_revision="study:5")
    with pytest.raises(IdempotencyConflict):
        await job_store.admit(**{**command, "input_data": {"question": "Changed"}}, input_revision="study:4")


async def test_owner_limit_is_shared_and_duplicates_do_not_consume_slots(job_store: SQLJobStore) -> None:
    for index in range(3):
        await SQLJobStore(job_store.sessionmaker).admit(
            kind="research", scope_id=f"study-{index}", owner_id="owner-1",
            input_data={"index": index}, idempotency_key=f"command-{index}",
        )
    duplicate = await job_store.admit(
        kind="research", scope_id="study-0", owner_id="owner-1",
        input_data={"index": 0}, idempotency_key="command-0",
    )
    assert not duplicate.created
    with pytest.raises(AdmissionLimit):
        await SQLJobStore(job_store.sessionmaker).admit(
            kind="report", scope_id="study-4", owner_id="owner-1", input_data={},
        )
    other_owner = await job_store.admit(
        kind="research", scope_id="study-0", owner_id="owner-2",
        input_data={"index": 0}, idempotency_key="command-0",
    )
    assert other_owner.created


@pytest.mark.parametrize("timeout_s", [0, -1, float("inf"), float("nan"), 3601])
async def test_deadline_override_is_bounded(job_store: SQLJobStore, timeout_s: float) -> None:
    with pytest.raises(ValueError):
        await job_store.admit(
            kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, timeout_s=timeout_s,
        )


async def test_prepare_failure_rolls_back_admission(job_store: SQLJobStore) -> None:
    async def fail_prepare(session, job):
        raise ValueError("Preparation rejected")

    with pytest.raises(ValueError, match="Preparation rejected"):
        await job_store.admit(
            kind="research", scope_id="study-1", owner_id="owner-1", input_data={}, prepare=fail_prepare,
        )
    assert await job_store.running_count("owner-1") == 0