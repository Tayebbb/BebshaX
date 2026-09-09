"""Research failure recovery using isolated persistence and stubbed discovery."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base, DatasetSources, EvidenceClaims, ResearchRuns, Studies
from bebshax.research import service as research_service
from bebshax.research.service import ResearchEngineService
from bebshax.utils.explicit_failures import LLMUnavailable

_STUDY_ID = "study_exhibition_recovery"


@pytest.fixture
async def recovery_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            session.add(Studies(id=_STUDY_ID, title="Synthetic recovery study", status="in_progress"))
            session.add(EvidenceClaims(
                id="claim_existing_recovery",
                study_id=_STUDY_ID,
                claim_text="Synthetic fixture claim retained before discovery.",
            ))
            await session.commit()
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture
def recovering_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ResearchEngineService:
    monkeypatch.setattr(research_service, "_upload_dir", lambda: tmp_path)
    plan = SimpleNamespace(
        target_market="Synthetic shift workers",
        problem_areas=["Scheduling uncertainty"],
        behavioral_questions=[],
        economic_questions=[],
        competition_questions=[],
        market_questions=[],
        dataset_requirements=[],
        summary="Synthetic scheduling research plan.",
        source="llm",
        served_by="fixture/planner",
        target_countries=["US"],
        model_dump=lambda: {"source": "llm", "served_by": "fixture/planner"},
    )
    monkeypatch.setattr(research_service, "generate_structured_research_plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(research_service, "generate_research_queries", AsyncMock(return_value=SimpleNamespace(
        queries=["Synthetic shift scheduling evidence"], source="llm", served_by="fixture/queries",
    )))
    search = Mock()
    search.name = "fixture"
    search.search = AsyncMock(return_value=[])
    discovery = Mock()
    discovery.discover_and_process_datasets = AsyncMock(return_value=([], []))
    return ResearchEngineService(search_provider=search, vector_engine=Mock(), discovery_engine=discovery)


async def test_discovery_failed_flush_rolls_back_saves_failure_and_reraises_database_error(
    recovery_sessions: async_sessionmaker[AsyncSession],
    recovering_service: ResearchEngineService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[IntegrityError] = []

    async def fail_discovery(**kwargs) -> None:
        session = kwargs["session"]
        session.add(DatasetSources(id="dataset_rolled_back", study_id=_STUDY_ID, name="Uncommitted dataset"))
        session.add(EvidenceClaims(
            id="claim_existing_recovery", study_id=_STUDY_ID, claim_text="Duplicate synthetic claim.",
        ))
        try:
            await session.flush()
        except IntegrityError as error:
            assert session.is_active is False
            failures.append(error)
            raise

    monkeypatch.setattr(recovering_service.discovery_engine, "discover_and_process_datasets", fail_discovery)
    async with recovery_sessions() as session:
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None
        with pytest.raises(IntegrityError) as failure:
            await recovering_service.run_study_research(session, study)
        assert failures and failure.value is failures[0]
        assert session.is_active is True

    async with recovery_sessions() as session:
        run = (await session.execute(select(ResearchRuns))).scalar_one()
        assert run.status == run.current_step == "failed"
        assert run.completed_at is not None
        assert run.step_progress["discovering_datasets"]["status"] == "failed"
        assert run.step_progress["extracting_evidence"]["status"] == "pending"
        assert run.step_progress["summary"]["error_code"] == "run_failed"
        assert run.step_progress["summary"]["plan_source"] == "llm"
        assert "IntegrityError" in (run.error_message or "")
        assert "Duplicate synthetic claim" not in (run.error_message or "")
        assert await session.get(DatasetSources, "dataset_rolled_back") is None
        original = await session.get(EvidenceClaims, "claim_existing_recovery")
        assert original is not None
        assert original.claim_text == "Synthetic fixture claim retained before discovery."


async def test_non_database_discovery_failure_remains_an_explicit_warning(
    recovery_sessions: async_sessionmaker[AsyncSession],
    recovering_service: ResearchEngineService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recovering_service.discovery_engine, "discover_and_process_datasets", AsyncMock(
        side_effect=RuntimeError("Fixture discovery is unavailable"),
    ))
    async with recovery_sessions() as session:
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None
        run = await recovering_service.run_study_research(session, study)
        assert run.status == "completed"
        assert run.step_progress["discovering_datasets"]["status"] == "completed_with_warnings"
        assert run.step_progress["summary"]["dataset_discovery_error"] == "RuntimeError"
        assert run.step_progress["summary"]["claims_status"] == "no_evidence"


async def test_explicit_planning_failure_is_persisted_without_inventing_a_plan(
    recovery_sessions: async_sessionmaker[AsyncSession],
    recovering_service: ResearchEngineService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(research_service, "generate_structured_research_plan", AsyncMock(
        side_effect=LLMUnavailable("Research planning"),
    ))
    async with recovery_sessions() as session:
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None
        run = await recovering_service.run_study_research(session, study)
        assert run.status == "failed"
        assert run.step_progress["building_research_plan"]["status"] == "failed"
        assert run.step_progress["summary"]["error_code"] == "llm_unavailable"
        assert run.research_plan is None
        assert run.completed_at is not None


async def test_terminal_state_write_failure_is_not_swallowed(
    recovery_sessions: async_sessionmaker[AsyncSession],
    recovering_service: ResearchEngineService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence_error = SQLAlchemyError("Fixture terminal-state persistence failure")

    async def fail_discovery(**kwargs) -> None:
        monkeypatch.setattr(kwargs["session"], "commit", AsyncMock(side_effect=persistence_error))
        raise SQLAlchemyError("Fixture discovery database failure")

    monkeypatch.setattr(recovering_service.discovery_engine, "discover_and_process_datasets", fail_discovery)
    async with recovery_sessions() as session:
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None
        with pytest.raises(SQLAlchemyError) as failure:
            await recovering_service.run_study_research(session, study)
        assert failure.value is persistence_error