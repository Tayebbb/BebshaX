from __future__ import annotations

import hashlib
import json
import threading

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, DatasetSources


@pytest.fixture
async def dataset_lineage(tmp_path, monkeypatch):
    from bebshax.datasets import service as datasets

    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(datasets, "_upload_dir", lambda: root)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'datasets.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    original = root / "ds_lineage.json"
    original.write_text('[{"age": 20}, {"age": 40}]', encoding="utf-8")
    async with maker() as session:
        session.add(DatasetSources(
            id="ds_lineage", user_id="owner_one", name="Age fixture", source_type="url",
            source_url="https://example.test/dataset.csv", file_type="csv", file_path=str(original),
            content_hash=hashlib.sha256(b"age\n20\n40\n").hexdigest(), status="ready",
            row_count=2, column_count=1, schema_metadata={}, statistics={}, segments=[],
        ))
        await session.commit()

    async def fetch(url):
        return b"age\n25\n45\n", "text/csv"

    monkeypatch.setattr(datasets, "safe_fetch_dataset_bytes", fetch)
    try:
        yield datasets.DatasetService(maker, ml_generator=object()), maker, original
    finally:
        await engine.dispose()


async def test_refresh_publishes_immutable_versions_and_preserves_original(dataset_lineage):
    from pathlib import Path
    from bebshax.datasets.orm import DatasetVersions

    service, maker, original = dataset_lineage
    previous_bytes = original.read_bytes()
    refreshed, changed = await service.refresh_dataset("ds_lineage", user_id="owner_one")
    assert changed
    assert refreshed.file_type == "csv"
    assert refreshed.file_path != str(original)
    assert original.read_bytes() == previous_bytes
    assert json.loads(Path(refreshed.file_path).read_text()) == [{"age": 25}, {"age": 45}]
    async with maker() as session:
        versions = (await session.scalars(select(DatasetVersions).order_by(DatasetVersions.version))).all()
        assert [version.version for version in versions] == [1, 2]
        assert versions[0].original_file_path == str(original)
        assert versions[1].file_path == refreshed.file_path
        assert all(hashlib.sha256(Path(version.file_path).read_bytes()).hexdigest() == version.records_hash for version in versions)
    unchanged, changed = await service.refresh_dataset("ds_lineage", user_id="owner_one")
    assert not changed and unchanged.file_path == refreshed.file_path


async def test_refresh_database_failure_never_overwrites_old_file(dataset_lineage):
    service, maker, original = dataset_lineage
    previous_bytes = original.read_bytes()
    fired = False

    def fail_pointer_change(session, flush_context, instances):
        nonlocal fired
        if not fired and any(isinstance(row, DatasetSources) and row.file_path != str(original) for row in session.dirty):
            fired = True
            raise SQLAlchemyError("Synthetic pointer commit failure")

    sync_class = maker.class_.sync_session_class
    event.listen(sync_class, "before_flush", fail_pointer_change)
    try:
        with pytest.raises(SQLAlchemyError):
            await service.refresh_dataset("ds_lineage", user_id="owner_one")
    finally:
        event.remove(sync_class, "before_flush", fail_pointer_change)
    assert original.read_bytes() == previous_bytes
    async with maker() as session:
        assert (await session.get(DatasetSources, "ds_lineage")).file_path == str(original)


async def test_parse_and_profile_leave_the_event_loop_and_no_download_transaction(dataset_lineage, monkeypatch):
    from bebshax.datasets import service as datasets

    service, maker, _ = dataset_lineage
    caller_thread = threading.get_ident()
    visited = []
    active = set()
    original_parse = datasets.parse_dataset_bytes
    original_profile = datasets.profile_dataset

    def parse(*args, **kwargs):
        assert threading.get_ident() != caller_thread
        visited.append("parse")
        return original_parse(*args, **kwargs)

    def profile(*args, **kwargs):
        assert threading.get_ident() != caller_thread
        visited.append("profile")
        return original_profile(*args, **kwargs)

    def begun(session, transaction, connection):
        active.add(session)

    def ended(session, transaction):
        if transaction.parent is None:
            active.discard(session)

    async def fetch(url):
        assert not active
        return b"age\n25\n45\n", "text/csv"

    monkeypatch.setattr(datasets, "parse_dataset_bytes", parse)
    monkeypatch.setattr(datasets, "profile_dataset", profile)
    monkeypatch.setattr(datasets, "safe_fetch_dataset_bytes", fetch)
    sync_class = maker.class_.sync_session_class
    event.listen(sync_class, "after_begin", begun)
    event.listen(sync_class, "after_transaction_end", ended)
    try:
        await service.refresh_dataset("ds_lineage", user_id="owner_one")
    finally:
        event.remove(sync_class, "after_begin", begun)
        event.remove(sync_class, "after_transaction_end", ended)
    assert visited == ["parse", "profile"]


async def test_delete_records_cleanup_and_never_unlinks_a_shared_file(dataset_lineage):
    from bebshax.jobs.orm import JobFileCleanup

    service, maker, original = dataset_lineage
    async with maker() as session:
        session.add(DatasetSources(id="ds_shared_ref", user_id="owner_two", name="Other reference", source_type="upload", file_path=str(original), file_type="csv"))
        await session.commit()
    assert await service.delete_dataset("ds_lineage", user_id="owner_one")
    assert original.exists()
    async with maker() as session:
        cleanup = (await session.scalars(select(JobFileCleanup))).one()
        assert cleanup.status == "blocked"
        assert await session.get(DatasetSources, "ds_lineage") is None


async def test_delete_cleanup_failure_is_durable_and_retryable(dataset_lineage, monkeypatch):
    from pathlib import Path
    from bebshax.jobs.orm import JobFileCleanup

    service, maker, original = dataset_lineage
    unlink = Path.unlink

    def denied(path, *args, **kwargs):
        if path == original:
            raise PermissionError("synthetic locked file")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "unlink", denied)
        assert await service.delete_dataset("ds_lineage", user_id="owner_one")
    async with maker() as session:
        cleanup = (await session.scalars(select(JobFileCleanup))).one()
        assert cleanup.status == "failed"
    await service.cleanup_pending_files()
    assert not original.exists()
    async with maker() as session:
        cleanup = (await session.scalars(select(JobFileCleanup))).one()
        assert cleanup.status == "completed" and cleanup.attempts == 2


@pytest.mark.parametrize("source", ["url", "upload", "candidate"])
async def test_ingestion_starts_with_an_immutable_version(dataset_lineage, source, monkeypatch):
    from pathlib import Path
    from bebshax.datasets import service as datasets
    from bebshax.datasets.orm import DatasetVersions

    service, maker, _ = dataset_lineage
    caller_thread = threading.get_ident()
    original_parse = datasets.parse_dataset_bytes

    def parse(*args, **kwargs):
        assert threading.get_ident() != caller_thread
        return original_parse(*args, **kwargs)

    monkeypatch.setattr(datasets, "parse_dataset_bytes", parse)
    common = dict(name="New dataset", user_id="owner_one", file_type="csv")
    if source == "url":
        dataset = await service.ingest_from_url("https://example.test/new.csv", **common)
    elif source == "upload":
        dataset = await service.ingest_from_upload(b"age\n25\n45\n", "ages.csv", **common)
    else:
        dataset = await service.ingest_candidate_dataset(b"age\n25\n45\n", source_url="https://example.test/new.csv", **common)
    async with maker() as session:
        version = (await session.scalars(select(DatasetVersions).where(DatasetVersions.dataset_id == dataset.id))).one()
        assert version.version == 1
        assert version.file_path == dataset.file_path
        assert version.content_hash == dataset.content_hash
        assert version.file_type == dataset.file_type == "csv"
        assert version.records_hash == hashlib.sha256(Path(dataset.file_path).read_bytes()).hexdigest()