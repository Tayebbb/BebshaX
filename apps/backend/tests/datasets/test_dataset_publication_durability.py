from __future__ import annotations

import asyncio
import hashlib
import threading
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.datasets import service as dataset_module
from bebshax.datasets.orm import DatasetVersions
from bebshax.datasets.service import DatasetService
from bebshax.db.models import Base, DatasetSources
from bebshax.jobs.orm import JobFileCleanup
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.fake import FakeAdapter


@pytest.fixture
async def publication_service(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: uploads)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'publication.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = DatasetService(maker, llm=SingleAdapterLLMService(FakeAdapter([])))
    try:
        yield service, maker, uploads
    finally:
        await engine.dispose()


@pytest.mark.parametrize("entrypoint", ["upload", "discovered"])
async def test_cancelled_upload_journals_its_finished_file_publication(publication_service, monkeypatch, entrypoint):
    service, maker, uploads = publication_service
    published = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    publish = dataset_module._publish_records

    def blocked_publication(*args, **kwargs):
        result = publish(*args, **kwargs)
        loop.call_soon_threadsafe(published.set)
        if not release.wait(5):
            raise RuntimeError("Publication fixture was not released")
        return result

    monkeypatch.setattr(dataset_module, "_publish_records", blocked_publication)
    operation = service.ingest_from_upload(
        b"age,role\n25,student\n", "synthetic.csv", "Synthetic", user_id="owner-one",
    ) if entrypoint == "upload" else service.prepare_discovered_dataset(
        content=b"age,role\n25,student\n", name="Synthetic", description="Synthetic fixture",
        source_url="https://example.test/synthetic.csv", fetched_from="synthetic.csv", file_type="csv",
        content_type="text/csv", user_id="owner-one", study_id="study-one",
    )
    task = asyncio.create_task(operation)
    try:
        await asyncio.wait_for(published.wait(), 3)
        task.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    paths = set(uploads.glob("*.json"))
    assert len(paths) == 1
    async with maker() as session:
        assert list(await session.scalars(select(DatasetSources))) == []
        assert list(await session.scalars(select(DatasetVersions))) == []
        cleanup = list(await session.scalars(select(JobFileCleanup)))
        assert {Path(entry.file_path) for entry in cleanup} == paths
        assert all(entry.owner_id == "owner-one" for entry in cleanup)
    assert await service.cleanup_pending_files() == 1
    assert list(uploads.iterdir()) == []


async def test_refresh_publication_error_preserves_legacy_source_and_journals_copies(publication_service, monkeypatch):
    service, maker, uploads = publication_service
    original = uploads / "ds_legacy.json"
    original.write_bytes(b'[{"age": 20}]')
    async with maker() as session, session.begin():
        session.add(DatasetSources(
            id="ds_legacy", user_id="owner-one", name="Synthetic", source_type="url", source_url="https://example.test/synthetic.csv",
            file_type="csv", file_path=str(original), content_hash="original-hash", row_count=1, column_count=1,
        ))

    async def fetched(url):
        return b"age\n30\n", "text/csv"

    publish = dataset_module._publish_records
    attempts = []

    def fail_second_publication(*args, **kwargs):
        attempts.append(args[0])
        if len(attempts) == 2:
            raise OSError("Synthetic file publication failure")
        return publish(*args, **kwargs)

    monkeypatch.setattr(dataset_module, "safe_fetch_dataset_bytes", fetched)
    monkeypatch.setattr(dataset_module, "_publish_records", fail_second_publication)
    with pytest.raises(OSError, match="Synthetic file publication failure"):
        await service.refresh_dataset("ds_legacy", user_id="owner-one")
    copied_paths = set(uploads.glob("ds_legacy.v_*.json"))
    assert len(copied_paths) == 1
    async with maker() as session:
        dataset = await session.get(DatasetSources, "ds_legacy")
        assert dataset.file_path == str(original)
        assert dataset.content_hash == "original-hash"
        assert list(await session.scalars(select(DatasetVersions))) == []
        cleanup = list(await session.scalars(select(JobFileCleanup)))
        assert copied_paths <= {Path(entry.file_path) for entry in cleanup}
    await service.cleanup_pending_files()
    assert list(uploads.iterdir()) == [original]
    assert hashlib.sha256(original.read_bytes()).hexdigest() == hashlib.sha256(b'[{"age": 20}]').hexdigest()


async def test_partial_publication_is_journaled_before_writing_and_can_be_erased(publication_service, monkeypatch):
    service, maker, uploads = publication_service
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def partial_publication(dataset_id, records, *, version_key):
        publication = dataset_module._records_publication(dataset_id, records, version_key)
        Path(publication[1]).write_bytes(records[:4])
        loop.call_soon_threadsafe(entered.set)
        if not release.wait(5):
            raise RuntimeError("Publication fixture was not released")
        raise OSError("Synthetic interrupted write")

    monkeypatch.setattr(dataset_module, "_publish_records", partial_publication)
    task = asyncio.create_task(service.ingest_from_upload(
        b"age\n25\n", "synthetic.csv", "Synthetic", user_id="owner-one",
    ))
    try:
        await asyncio.wait_for(entered.wait(), 3)
        async with maker() as session:
            [entry] = list(await session.scalars(select(JobFileCleanup)))
            assert entry.status == "running"
            assert Path(entry.file_path).exists()
    finally:
        release.set()
        with pytest.raises(OSError, match="Synthetic interrupted write"):
            await task
    assert await service.cleanup_pending_files() == 1
    assert list(uploads.iterdir()) == []


async def test_shared_file_cleanup_retries_after_last_reference_is_deleted(publication_service):
    service, maker, uploads = publication_service
    original = uploads / "ds_original.json"
    original.write_bytes(b'[{"age": 25}]')
    async with maker() as session, session.begin():
        session.add_all([
            DatasetSources(id="ds_original", user_id="owner-one", name="Synthetic", file_path=str(original)),
            DatasetSources(id="ds_reference", user_id="owner-two", name="Synthetic reference", file_path=str(original)),
        ])
    assert await service.delete_dataset("ds_original", user_id="owner-one")
    assert original.exists()
    assert await service.delete_dataset("ds_reference", user_id="owner-two")
    await service.cleanup_pending_files()
    assert not original.exists()


async def test_repeated_cancellation_keeps_cpu_slot_until_thread_finishes(publication_service):
    service, _, _ = publication_service
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def work():
        loop.call_soon_threadsafe(started.set)
        if not release.wait(5):
            raise RuntimeError("CPU fixture was not released")

    task = asyncio.create_task(service._cpu(work))
    try:
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        completed, _ = await asyncio.wait({task}, timeout=0.05)
        assert not completed, "Cancellation released a still-running CPU worker"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task