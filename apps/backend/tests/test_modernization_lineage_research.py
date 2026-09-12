from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, DatasetCandidates, DatasetSources, Studies


@pytest.fixture
async def research_lineage(tmp_path, monkeypatch):
    from bebshax.research import service as research

    monkeypatch.setattr(research, "_upload_dir", lambda: tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'research.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=True)
    async with maker() as session:
        session.add(Studies(id="research_study", title="Study", prompt="Original idea", user_id="owner_one", target_audience="Synthetic users"))
        session.add(DatasetCandidates(
            id="candidate_one", study_id="research_study", user_id="owner_one", source="fixture", external_id="one",
            name="Original candidate", url="https://example.test/data", download_url="https://example.test/data.csv", format="csv",
        ))
        await session.commit()
    try:
        yield maker
    finally:
        await engine.dispose()


async def test_candidate_import_captures_inputs_before_releasing_read_transaction(research_lineage, monkeypatch):
    from bebshax.research import service as research

    maker = research_lineage
    seen = []

    async def materialize(**kwargs):
        assert not kwargs["session"].in_transaction()
        seen.append((kwargs["name"], kwargs["declared_format"], kwargs["download_url"]))
        dataset = DatasetSources(id="imported_one", study_id="research_study", user_id="owner_one", name=kwargs["name"], file_type=kwargs["declared_format"], row_count=2, column_count=1)
        kwargs["session"].add(dataset)
        return dataset

    monkeypatch.setattr(research, "materialize_candidate", materialize)
    service = research.ResearchEngineService(search_provider=SimpleNamespace(), vector_engine=SimpleNamespace(), discovery_engine=SimpleNamespace())
    async with maker() as session:
        imported = await service.import_candidate_dataset(session, "research_study", "candidate_one", "owner_one")
        assert imported.id == "imported_one" and imported.file_type == "csv"
    assert seen == [("Original candidate", "csv", "https://example.test/data.csv")]


async def test_research_snapshots_study_before_expiring_commits(research_lineage, monkeypatch):
    from bebshax.research import service as research

    maker = research_lineage
    plan = SimpleNamespace(
        target_market="Synthetic users", problem_areas=[], behavioral_questions=[], economic_questions=[],
        competition_questions=[], market_questions=[], dataset_requirements=[], summary="A synthetic plan",
        source="llm", served_by="fake/planner", target_countries=[], model_dump=lambda: {"source": "llm"},
    )
    async with maker() as session:
        async def planning(**kwargs):
            assert not session.in_transaction()
            assert kwargs["idea"] == "Original idea" and kwargs["target_audience"] == "Synthetic users"
            return plan

        async def queries(**kwargs):
            assert not session.in_transaction()
            return SimpleNamespace(queries=["Original idea"], source="llm", served_by="fake/query")

        async def discovery(**kwargs):
            assert not session.in_transaction()
            return [], []

        monkeypatch.setattr(research, "generate_structured_research_plan", planning)
        monkeypatch.setattr(research, "generate_research_queries", queries)
        service = research.ResearchEngineService(
            search_provider=SimpleNamespace(name="fake", search=AsyncMock(return_value=[])),
            vector_engine=SimpleNamespace(), discovery_engine=SimpleNamespace(discover_and_process_datasets=discovery),
        )
        study = await session.get(Studies, "research_study")
        run = await service.run_study_research(session, study, user_id="owner_one")
        assert run.status == "completed", run.error_message


async def test_research_job_persists_run_reference_before_planning(research_lineage, monkeypatch):
    from sqlalchemy import select
    from bebshax.jobs.orm import JobCheckpoints
    from bebshax.jobs.runtime import JobRuntime
    from bebshax.jobs.store import SQLJobStore
    from bebshax.research import service as research
    from bebshax.utils.explicit_failures import LLMUnavailable

    maker = research_lineage
    async with maker().bind.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = SQLJobStore(maker)
    runtime = JobRuntime(store)

    async def planning(**kwargs):
        async with maker() as session:
            checkpoint = await session.scalar(select(JobCheckpoints).where(JobCheckpoints.item_key == "research_run"))
            assert checkpoint.status == "completed" and checkpoint.result_refs["run_id"]
        raise LLMUnavailable("Synthetic planning failure")

    monkeypatch.setattr(research, "generate_structured_research_plan", planning)
    service = research.ResearchEngineService(search_provider=SimpleNamespace(name="fake"), vector_engine=SimpleNamespace(), discovery_engine=SimpleNamespace())

    async def runner(job):
        async with maker() as session:
            study = await session.get(Studies, "research_study")
            await service.run_study_research(session, study, user_id="owner_one", job=job)

    admitted = await runtime.start(kind="research_generation", scope_id="research_study", owner_id="owner_one", input_data={}, runner=runner)
    await runtime.drain()
    persisted = await store.get(admitted["job_id"], kind="research_generation", scope_id="research_study", owner_id="owner_one")
    assert persisted["status"] == "failed" and persisted["error_code"] == "llm_unavailable"
    assert persisted["result_refs"]["run_id"]
    await runtime.shutdown()


async def test_research_materializer_profiles_off_thread_and_versions_files(research_lineage, monkeypatch, tmp_path):
    import threading
    from sqlalchemy import select
    from bebshax.datasets import service as datasets
    from bebshax.datasets.discovery import engine as discovery
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.research import service as research

    monkeypatch.setattr(datasets, "_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(discovery, "_upload_dir", lambda: tmp_path)
    caller_thread = threading.get_ident()
    parser = datasets.parse_dataset_bytes

    def checked_parse(*args, **kwargs):
        assert threading.get_ident() != caller_thread
        return parser(*args, **kwargs)

    monkeypatch.setattr(datasets, "parse_dataset_bytes", checked_parse)
    monkeypatch.setattr(discovery, "parse_dataset_bytes", checked_parse)
    async with research_lineage() as session:
        imported = await research.materialize_candidate(
            session=session, study_id="research_study", user_id="owner_one", name="Fixture",
            description="Synthetic", source="fixture", publisher="Fixture", license_text="CC0",
            url="https://example.test/data", download_url=None, declared_format="csv",
            raw_data_content="age\n25\n45\n",
        )
        imported_id = imported.id
        await session.commit()
    async with research_lineage() as session:
        dataset = await session.get(DatasetSources, imported_id)
        version = (await session.scalars(select(DatasetVersions).where(DatasetVersions.dataset_id == imported_id))).one()
        assert version.version == 1 and version.file_path == dataset.file_path
        assert dataset.schema_metadata["is_sample"] is False


async def test_research_default_discovery_uses_versioned_materializer(research_lineage, monkeypatch, tmp_path):
    from sqlalchemy import select
    from bebshax.datasets import service as datasets
    from bebshax.datasets.discovery.base_adapter import DatasetCandidateData
    from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
    from bebshax.datasets.discovery import engine as discovery_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.research import service as research

    monkeypatch.setattr(datasets, "_upload_dir", lambda: tmp_path)
    monkeypatch.setattr(discovery_module, "_upload_dir", lambda: tmp_path)
    candidate = DatasetCandidateData(
        source="fixture", external_id="versioned", name="A real tabular fixture", description="Synthetic test data",
        url="https://example.test/data", publisher="Fixture", license="CC0", format="csv", raw_data_content="age\n25\n45\n",
    )
    adapter = SimpleNamespace(source_name="fixture", search=AsyncMock(return_value=[candidate]))
    evaluated = SimpleNamespace(candidate=candidate, selection_status="selected", selection_reason="Fixture", evaluation_details={},
                                relevance_score=0.8, quality_score=0.8, is_selected=True)
    discovery = DatasetDiscoveryEngine(adapters=[adapter], evaluator=SimpleNamespace(evaluate_candidates=lambda *args: [evaluated]))
    service = research.ResearchEngineService(search_provider=SimpleNamespace(), vector_engine=SimpleNamespace(), discovery_engine=discovery)
    async with research_lineage() as session:
        candidates, imported = await service.discovery_engine.discover_and_process_datasets(
            session, "research_study", "owner_one", None, "Idea", [], [], countries=[],
        )
        assert len(imported) == len(candidates) == 1
    async with research_lineage() as session:
        assert len((await session.scalars(select(DatasetVersions))).all()) == 1