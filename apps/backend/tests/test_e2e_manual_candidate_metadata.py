"""Manual imports must not materialize discovery's metadata placeholders."""

import copy
import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.api.errors import APIError
from bebshax.db.models import DatasetCandidates, DatasetSources
from bebshax.research.service import ResearchEngineService


@pytest.fixture
async def manual_candidate_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with database.begin() as connection:
            await connection.run_sync(DatasetCandidates.__table__.create)
            await connection.run_sync(DatasetSources.__table__.create)
        yield async_sessionmaker(database, expire_on_commit=False)
    finally:
        await database.dispose()


@pytest.fixture
def manual_candidate() -> DatasetCandidates:
    return DatasetCandidates(
        id="candidate-manual-metadata",
        study_id="study-manual-metadata",
        user_id="user-manual-metadata",
        source="public-statistics",
        external_id="population-statistics",
        name="Population statistics",
        description="Population statistics by country.",
        url="https://example.org/datasets/population",
        download_url="https://example.org/population.csv",
        publisher="Public statistics office",
        license="CC-BY-4.0",
        format="csv",
        selection_status="discovered",
        selection_reason="Relevant population evidence.",
        evaluation_details={"is_sample": False},
    )


@pytest.fixture
def manual_import_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[ResearchEngineService, AsyncMock, Path]:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("bebshax.research.service._upload_dir", lambda: upload_dir)
    monkeypatch.setattr("bebshax.datasets.discovery.engine._upload_dir", lambda: upload_dir)
    download = AsyncMock(return_value=(
        b"country,population\nCountry,100\nOther,200\n",
        {"url": "https://example.org/population.csv", "content_type": "text/csv"},
    ))
    monkeypatch.setattr("bebshax.datasets.discovery.engine.fetch_resource_bytes", download)
    service = ResearchEngineService(
        search_provider=Mock(), vector_engine=Mock(), discovery_engine=Mock(),
    )
    return service, download, upload_dir


@pytest.mark.asyncio
@pytest.mark.parametrize(("field", "limit"), [("name", 256), ("license", 128)])
async def test_manual_import_rejects_invalid_metadata_without_writes(
    manual_candidate_db, manual_candidate: DatasetCandidates, manual_import_service,
    monkeypatch: pytest.MonkeyPatch, field: str, limit: int,
) -> None:
    service, download, upload_dir = manual_import_service
    raw_metadata = {
        "name": manual_candidate.name,
        "license": manual_candidate.license,
        "description": "Full original description " + "D" * 2048,
        field: "X" * (limit + 1),
    }
    setattr(manual_candidate, field, f"See evaluation_details.raw_metadata.{field}")
    manual_candidate.selection_status = "import_failed"
    manual_candidate.selection_reason = f"Not imported: {field} exceeds storage limits."
    manual_candidate.evaluation_details = {
        "raw_metadata": raw_metadata,
        "metadata_errors": {field: {"actual_length": limit + 1, "max_length": limit}},
        "import_error": manual_candidate.selection_reason,
    }
    async with manual_candidate_db() as session:
        session.add(manual_candidate)
        await session.commit()
        await session.refresh(manual_candidate)
        original = {
            column.name: copy.deepcopy(getattr(manual_candidate, column.name))
            for column in DatasetCandidates.__table__.columns
        }

    async with manual_candidate_db() as session:
        commit = AsyncMock(wraps=session.commit)
        monkeypatch.setattr(session, "commit", commit)
        with pytest.raises(APIError) as caught:
            await service.import_candidate_dataset(
                session, manual_candidate.study_id, manual_candidate.id, manual_candidate.user_id,
            )
        assert caught.value.status_code == 422
        assert caught.value.error_code == "invalid_metadata"
        assert "metadata exceeds storage limits" in caught.value.detail
        assert "evaluation_details.raw_metadata" in caught.value.detail
        download.assert_not_called()
        commit.assert_not_awaited()
        assert not session.new
        assert not session.dirty
        assert not session.deleted

    async with manual_candidate_db() as session:
        persisted = await session.get(DatasetCandidates, manual_candidate.id)
        assert persisted is not None
        assert {
            column.name: getattr(persisted, column.name)
            for column in DatasetCandidates.__table__.columns
        } == original
        assert list((await session.scalars(select(DatasetSources))).all()) == []
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("evaluation_details", [None, {}, {"metadata_errors": {}}])
@pytest.mark.parametrize("selection_status", ["discovered", "import_failed"])
async def test_manual_import_valid_metadata_still_materializes(
    manual_candidate_db, manual_candidate: DatasetCandidates, manual_import_service,
    evaluation_details: dict | None, selection_status: str,
) -> None:
    service, download, upload_dir = manual_import_service
    manual_candidate.evaluation_details = evaluation_details
    manual_candidate.selection_status = selection_status
    async with manual_candidate_db() as session:
        session.add(manual_candidate)
        await session.commit()

    async with manual_candidate_db() as session:
        imported = await service.import_candidate_dataset(
            session, manual_candidate.study_id, manual_candidate.id, manual_candidate.user_id,
        )
        imported_id = imported.id
    download.assert_awaited_once_with(manual_candidate.download_url, http_client=None)
    async with manual_candidate_db() as session:
        persisted = await session.get(DatasetCandidates, manual_candidate.id)
        dataset = (await session.scalars(select(DatasetSources))).one()
        assert persisted is not None
        assert persisted.selection_status == "imported"
        assert persisted.imported_dataset_id == dataset.id == imported_id
        assert persisted.evaluation_details == evaluation_details
        assert persisted.name == dataset.name == manual_candidate.name
        assert persisted.license == manual_candidate.license
        assert f"License: {manual_candidate.license}" in dataset.description
        assert persisted.sample_rows == dataset.row_count == 2
        assert persisted.sample_columns == dataset.column_count == 2
        assert dataset.status == "ready"
        assert dataset.study_id == manual_candidate.study_id
        assert dataset.user_id == manual_candidate.user_id
        files = list(upload_dir.iterdir())
        assert files == [Path(dataset.file_path)]
        assert len(json.loads(files[0].read_text(encoding="utf-8"))) == 2