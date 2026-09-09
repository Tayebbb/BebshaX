"""Offline discovery regressions enforcing PostgreSQL varchar limits."""

import hashlib
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import String, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.datasets.discovery.base_adapter import DatasetCandidateData
from bebshax.datasets.discovery.ckan_adapter import CKANDatasetAdapter
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.datasets.discovery.evaluator import DatasetEvaluator
from bebshax.db.models import DatasetCandidates, DatasetSources


@pytest.fixture
def metadata_candidate() -> DatasetCandidateData:
    candidate = CKANDatasetAdapter.hdx()._to_candidate(
        {
            "name": "population-statistics",
            "title": "Population statistics",
            "notes": "Population statistics by country and year.",
            "organization": {"title": "Public statistics office"},
            "license_title": "Creative Commons Attribution",
            "license_url": "https://example.org/license",
            "groups": [{"name": "population", "title": "Region " + "A" * 123}],
            "tags": [{"name": "population"}],
            "resources": [],
        }
    )
    assert candidate is not None
    return candidate


def _overflows(candidate: DatasetCandidateData) -> dict[str, tuple[int, int]]:
    return {
        column.name: (len(value), column.type.length)
        for column in DatasetCandidates.__table__.columns
        if isinstance(column.type, String)
        and column.type.length is not None
        and isinstance(value := getattr(candidate, column.name, None), str)
        and len(value) > column.type.length
    }


def test_ckan_geography_exceeds_128_but_external_id_does_not(
    metadata_candidate: DatasetCandidateData,
) -> None:
    assert _overflows(metadata_candidate) == {"geographic_coverage": (130, 128)}
    assert DatasetCandidates.__table__.c.external_id.type.length == 256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("source", 128),
        ("external_id", 256),
        ("name", 256),
        ("publisher", 256),
        ("license", 128),
        ("format", 64),
        ("geographic_coverage", 128),
        ("population_coverage", 128),
    ],
)
async def test_overlong_metadata_retained_without_poisoning_batch(
    metadata_candidate: DatasetCandidateData,
    field: str,
    limit: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = metadata_candidate.model_copy(
        update={"geographic_coverage": "Country", field: "V" * limit}
    )
    invalid = valid.model_copy(
        update={
            "external_id": "overlong-metadata",
            field: "X" * (limit + 1),
            "raw_data_content": "country,population\nCountry,100\n",
        }
    )
    adapter = AsyncMock()
    adapter.search.return_value = [invalid, valid]
    evaluator = DatasetEvaluator(max_auto_select=0)
    results = evaluator.evaluate_candidates([invalid, valid], "population", [], [])
    results.sort(key=lambda result: result.candidate != invalid)
    for result in results:
        result.is_selected = True
    monkeypatch.setattr(evaluator, "evaluate_candidates", lambda *args: results)
    imported_source = DatasetSources(id="imported-valid", row_count=1, column_count=2)
    materialize = AsyncMock(return_value=imported_source)
    monkeypatch.setattr("bebshax.datasets.discovery.engine.materialize_candidate", materialize)

    database = create_async_engine("sqlite+aiosqlite:///:memory:")

    def enforce_varchar_limits(mapper, connection, target: DatasetCandidates) -> None:
        for column in target.__table__.columns:
            value = getattr(target, column.name)
            if isinstance(column.type, String) and column.type.length and isinstance(value, str):
                assert len(value) <= column.type.length, (
                    f"{column.name}: {len(value)} exceeds varchar({column.type.length})"
                )

    event.listen(DatasetCandidates, "before_insert", enforce_varchar_limits)
    try:
        async with database.begin() as connection:
            await connection.run_sync(DatasetCandidates.__table__.create)
        maker = async_sessionmaker(database, expire_on_commit=False)
        discovery = DatasetDiscoveryEngine(adapters=[adapter], evaluator=evaluator)
        async with maker() as session:
            candidates, imported = await discovery.discover_and_process_datasets(
                session=session,
                study_id="study-metadata",
                user_id="user-metadata",
                run_id="run-metadata",
                idea="population",
                queries=[],
                requirements=[],
            )
        assert len(candidates) == 2
        assert imported == [imported_source]
        materialize.assert_awaited_once()
        assert materialize.await_args.kwargs["raw_data_content"] is None
        assert materialize.await_args.kwargs["license_text"] == valid.license
        assert materialize.await_args.kwargs["source"] == valid.source
        assert materialize.await_args.kwargs["name"] == valid.name
        async with maker() as session:
            rows = list((await session.scalars(select(DatasetCandidates))).all())
        rejected = next(row for row in rows if row.selection_status == "import_failed")
        accepted = next(row for row in rows if row.selection_status == "imported")
        assert accepted.external_id == valid.external_id
        assert accepted.license == valid.license
        assert getattr(accepted, field) == getattr(valid, field)
        assert "raw_metadata" not in accepted.evaluation_details
        assert accepted.imported_dataset_id == imported_source.id
        assert rejected.evaluation_details["raw_metadata"] == invalid.model_dump(mode="json")
        assert rejected.evaluation_details["metadata_errors"] == {
            field: {"actual_length": limit + 1, "max_length": limit}
        }
        assert field in rejected.selection_reason
        assert str(limit + 1) in rejected.selection_reason
        assert str(limit) in rejected.selection_reason
        if field == "license":
            assert rejected.license == "See evaluation_details.raw_metadata.license"
        else:
            assert rejected.license == invalid.license
        if field in {"source", "external_id"}:
            expected_id = "sha256:" + hashlib.sha256(getattr(invalid, field).encode("utf-8")).hexdigest()
            assert getattr(rejected, field) == expected_id
        assert getattr(rejected, field) != getattr(invalid, field)[:limit]
    finally:
        event.remove(DatasetCandidates, "before_insert", enforce_varchar_limits)
        await database.dispose()