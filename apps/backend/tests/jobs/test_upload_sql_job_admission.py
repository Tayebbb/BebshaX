from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from bebshax.api.errors import APIError
from bebshax.jobs.store import MAX_RUNNING_JOBS_PER_USER, SQLJobStore


@pytest.mark.parametrize("job_state", ["queued", "running"])
@pytest.mark.parametrize("active_jobs", range(MAX_RUNNING_JOBS_PER_USER + 1))
async def test_owner_capacity_uses_active_durable_jobs(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore, active_jobs: int, job_state: str,
) -> None:
    admission = sql_upload_context.admission
    for index in range(active_jobs):
        admitted = await job_store.admit(
            kind="dataset_upload", scope_id=f"dataset-{index}", owner_id="owner-1", input_data={},
        )
        if job_state == "running":
            assert await job_store.claim(admitted.job["job_id"], worker_id="upload-test-worker") is not None

    if active_jobs == MAX_RUNNING_JOBS_PER_USER:
        with pytest.raises(APIError) as rejected:
            async with admission.admit(sql_upload_context.request()):
                pytest.fail("An owner at the durable job limit must not be admitted")
        assert rejected.value.status_code == 429
        assert rejected.value.error_code == "too_many_jobs"
    else:
        async with admission.admit(sql_upload_context.request()):
            assert admission.users == {"owner-1": 1}

    assert admission.users == {}
    assert not admission.slots.locked()
    assert await job_store.running_count("owner-1") == active_jobs


async def test_other_owners_durable_jobs_do_not_consume_upload_capacity(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore,
) -> None:
    for index in range(MAX_RUNNING_JOBS_PER_USER):
        await job_store.admit(
            kind="research", scope_id=f"study-{index}", owner_id="owner-2", input_data={},
        )

    admission = sql_upload_context.admission
    async with admission.admit(sql_upload_context.request("owner-1")):
        assert admission.users == {"owner-1": 1}
        with pytest.raises(APIError) as rejected:
            async with admission.admit(sql_upload_context.request("owner-2")):
                pytest.fail("The other owner's durable limit must still be enforced")
        assert rejected.value.status_code == 429
        assert rejected.value.error_code == "too_many_jobs"
        assert admission.users == {"owner-1": 1}
    assert admission.users == {}


async def test_cancelled_durable_jobs_do_not_consume_upload_capacity(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore,
) -> None:
    for index in range(MAX_RUNNING_JOBS_PER_USER):
        admitted = await job_store.admit(
            kind="dataset_upload", scope_id=f"dataset-{index}", owner_id="owner-1", input_data={},
        )
        await job_store.cancel_queued(admitted.job["job_id"])

    assert await job_store.running_count("owner-1") == 0
    async with sql_upload_context.admission.admit(sql_upload_context.request()):
        assert sql_upload_context.admission.users == {"owner-1": 1}
    assert sql_upload_context.admission.users == {}


async def test_global_upload_limit_is_shared_across_owners_and_released(
    sql_upload_context: SimpleNamespace,
) -> None:
    admission = sql_upload_context.admission
    async with AsyncExitStack() as reservations:
        for index in range(MAX_RUNNING_JOBS_PER_USER):
            owner_id = "owner-1" if index == 0 else "owner-2"
            await reservations.enter_async_context(admission.admit(sql_upload_context.request(owner_id)))
        assert admission.users == {"owner-1": 1, "owner-2": MAX_RUNNING_JOBS_PER_USER - 1}
        with pytest.raises(APIError) as rejected:
            async with admission.admit(sql_upload_context.request("owner-1")):
                pytest.fail("Global upload capacity must reject without waiting")
        assert rejected.value.status_code == 429
        assert rejected.value.error_code == "too_many_jobs"

    assert admission.users == {}
    async with admission.admit(sql_upload_context.request("owner-1")):
        assert admission.users == {"owner-1": 1}


async def test_same_owner_reservations_are_rechecked_after_concurrent_durable_counts(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore, held_upload_job_counts: SimpleNamespace,
) -> None:
    await job_store.admit(kind="research", scope_id="study-1", owner_id="owner-1", input_data={})
    admission = sql_upload_context.admission
    outcomes: asyncio.Queue[APIError | None] = asyncio.Queue()
    release_requests = asyncio.Event()

    async def upload() -> None:
        try:
            async with admission.admit(sql_upload_context.request()):
                outcomes.put_nowait(None)
                await release_requests.wait()
        except APIError as rejected:
            outcomes.put_nowait(rejected)

    requests = [asyncio.create_task(upload()) for _ in range(MAX_RUNNING_JOBS_PER_USER)]
    try:
        count_releases = [
            await asyncio.wait_for(held_upload_job_counts.waiters.get(), timeout=5)
            for _ in requests
        ]
        assert admission.users == {}
        for release in count_releases:
            release.set()
        results = [await asyncio.wait_for(outcomes.get(), timeout=5) for _ in requests]
        assert results.count(None) == MAX_RUNNING_JOBS_PER_USER - 1
        rejections = [result for result in results if result is not None]
        assert len(rejections) == 1
        assert rejections[0].status_code == 429
        assert rejections[0].error_code == "too_many_jobs"
        assert admission.users == {"owner-1": MAX_RUNNING_JOBS_PER_USER - 1}
        release_requests.set()
        await asyncio.gather(*requests)
    finally:
        for request in requests:
            request.cancel()
        await asyncio.gather(*requests, return_exceptions=True)
    assert admission.users == {}
    assert not admission.slots.locked()


async def test_reservations_released_during_durable_count_are_not_restored(
    sql_upload_context: SimpleNamespace, held_upload_job_counts: SimpleNamespace,
) -> None:
    admission = sql_upload_context.admission
    held_upload_job_counts.enabled = False
    entered = asyncio.Event()
    release_request = asyncio.Event()

    async def upload() -> None:
        async with admission.admit(sql_upload_context.request()):
            entered.set()
            await release_request.wait()

    async with AsyncExitStack() as previous_reservations:
        await previous_reservations.enter_async_context(admission.admit(sql_upload_context.request()))
        held_upload_job_counts.enabled = True
        request = asyncio.create_task(upload())
        try:
            release_count = await asyncio.wait_for(held_upload_job_counts.waiters.get(), timeout=5)
            await previous_reservations.aclose()
            assert admission.users == {}
            release_count.set()
            await asyncio.wait_for(entered.wait(), timeout=5)
            assert admission.users == {"owner-1": 1}
            release_request.set()
            await request
        finally:
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
    assert admission.users == {}


@pytest.mark.parametrize("phase", ["count", "body"])
@pytest.mark.parametrize("termination", ["failure", "cancel"])
async def test_failure_or_cancellation_releases_owner_and_global_capacity(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore, monkeypatch: pytest.MonkeyPatch,
    phase: str, termination: str,
) -> None:
    admission = sql_upload_context.admission
    original_count = job_store.running_count
    paused = asyncio.Event()
    release = asyncio.Event()

    async def pause() -> None:
        paused.set()
        await release.wait()
        raise RuntimeError("Synthetic upload failure")

    async def controlled_count(owner_id: str) -> int:
        count = await original_count(owner_id)
        if phase == "count":
            await pause()
        return count

    monkeypatch.setattr(job_store, "running_count", controlled_count)

    async def upload() -> None:
        async with admission.admit(sql_upload_context.request()):
            await pause()

    request = asyncio.create_task(upload())
    try:
        await asyncio.wait_for(paused.wait(), timeout=5)
        assert admission.users == ({} if phase == "count" else {"owner-1": 1})
        if termination == "cancel":
            request.cancel()
        else:
            release.set()
        expected_error = asyncio.CancelledError if termination == "cancel" else RuntimeError
        with pytest.raises(expected_error):
            await request
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)

    monkeypatch.setattr(job_store, "running_count", original_count)
    assert admission.users == {}
    async with AsyncExitStack() as reservations:
        for _ in range(MAX_RUNNING_JOBS_PER_USER):
            await reservations.enter_async_context(admission.admit(sql_upload_context.request()))
        assert admission.users == {"owner-1": MAX_RUNNING_JOBS_PER_USER}
    assert admission.users == {}


async def test_unknown_owner_is_rejected_before_durable_count_and_releases_capacity(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_count = job_store.running_count

    async def forbidden_count(owner_id: str) -> int:
        pytest.fail("Authentication must finish before querying the durable owner count")

    monkeypatch.setattr(job_store, "running_count", forbidden_count)
    with pytest.raises(HTTPException) as rejected:
        async with sql_upload_context.admission.admit(sql_upload_context.request("unknown-owner")):
            pytest.fail("An unknown owner must not be admitted")
    assert rejected.value.status_code == 401
    assert sql_upload_context.admission.users == {}
    monkeypatch.setattr(job_store, "running_count", original_count)
    async with sql_upload_context.admission.admit(sql_upload_context.request()):
        assert sql_upload_context.admission.users == {"owner-1": 1}


async def test_durable_upload_and_live_reservation_remain_conservatively_counted(
    sql_upload_context: SimpleNamespace, job_store: SQLJobStore,
) -> None:
    admission = sql_upload_context.admission
    async with admission.admit(sql_upload_context.request()):
        await job_store.admit(
            kind="dataset_upload", scope_id="dataset-1", owner_id="owner-1", input_data={},
        )
        async with admission.admit(sql_upload_context.request()):
            assert await job_store.running_count("owner-1") == 1
            assert admission.users == {"owner-1": 2}
            with pytest.raises(APIError) as rejected:
                async with admission.admit(sql_upload_context.request()):
                    pytest.fail("A queued upload keeps its live reservation until the request exits")
            assert rejected.value.status_code == 429
            assert rejected.value.error_code == "too_many_jobs"

    assert admission.users == {}
    async with AsyncExitStack() as reservations:
        for _ in range(MAX_RUNNING_JOBS_PER_USER - 1):
            await reservations.enter_async_context(admission.admit(sql_upload_context.request()))
        assert admission.users == {"owner-1": MAX_RUNNING_JOBS_PER_USER - 1}
    assert admission.users == {}