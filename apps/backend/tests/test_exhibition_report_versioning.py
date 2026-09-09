"""Report allocation regressions; PostgreSQL must verify real lock contention."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base, EvidenceClaims, Studies, StudyReports
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.pools import POOLS
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import TaskType
from bebshax.research.report_service import StudyReportService
from bebshax.utils.explicit_failures import UnusableModelOutput

_STUDY_ID = "study_exhibition_report_versions"
_REPORT_REPLY = json.dumps({"executive_summary": "The stored scheduling claim remains an unvalidated inference."})


@pytest.fixture
async def report_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'report_versions.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=True)
        async with session_factory() as session:
            session.add(Studies(
                id=_STUDY_ID, title="Synthetic scheduling study", status="in_progress", step=4,
            ))
            session.add(EvidenceClaims(
                id="claim_exhibition_versions", study_id=_STUDY_ID,
                claim_text="Scheduling reminders may help synthetic shift workers.", status="inference",
            ))
            await session.commit()
        yield session_factory
    finally:
        await engine.dispose()


def _report_router(reply: str = _REPORT_REPLY) -> tuple[PoolRouter, FakeAdapter]:
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="pollinations", model="deepseek-r1", context_window=100_000),
        reply=reply,
    )])
    return PoolRouter({name: adapter for pool in POOLS.values() for name in pool.adapters}), adapter


async def test_overlapping_generations_allocate_versions_after_each_model_reply(
    report_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    slow_router, slow_adapter = _report_router()
    fast_router, fast_adapter = _report_router()
    fast_reports: list[StudyReports] = []
    original_slow_complete = slow_adapter.complete
    original_fast_complete = fast_adapter.complete

    async with report_sessions() as slow_session, report_sessions() as fast_session:
        async def fast_complete(candidate, request):
            assert not fast_session.in_transaction()
            return await original_fast_complete(candidate, request)

        async def slow_complete(candidate, request):
            assert not slow_session.in_transaction()
            fast_reports.append(await StudyReportService(fast_session, fast_router).generate_report(
                _STUDY_ID, custom_title="Faster report",
            ))
            await fast_session.rollback()
            return await original_slow_complete(candidate, request)

        monkeypatch.setattr(fast_adapter, "complete", fast_complete)
        monkeypatch.setattr(slow_adapter, "complete", slow_complete)
        delayed = await StudyReportService(slow_session, slow_router).generate_report(
            _STUDY_ID, custom_title="Delayed report",
        )
        assert delayed.version == 2
        assert delayed.metrics["llm_request_id"] == slow_adapter.requests[0].request_id
        assert fast_reports
        assert len(slow_adapter.requests) == len(fast_adapter.requests) == 1
        assert slow_adapter.requests[0].task == fast_adapter.requests[0].task == TaskType.REPORT_GENERATION

    async with report_sessions() as session:
        reports = list((await session.execute(select(StudyReports).order_by(StudyReports.version))).scalars())
        assert [(report.version, report.title) for report in reports] == [(1, "Faster report"), (2, "Delayed report")]
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None and study.findings is not None
        assert study.findings["version"] == 2
        assert study.findings["report_id"] == reports[1].id


async def test_study_lock_precedes_max_in_the_final_transaction_only(
    report_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    router, adapter = _report_router()
    operations: list[tuple[str, object]] = []

    async with report_sessions() as session:
        original_execute = session.execute
        original_complete = adapter.complete

        async def execute(statement, *args, **kwargs):
            compiled = statement.compile(dialect=postgresql.dialect())
            sql = str(compiled)
            if "FOR UPDATE" in sql:
                assert _STUDY_ID in compiled.params.values()
                operations.append(("lock", session.sync_session.get_transaction()))
            elif "max(study_reports.version)" in sql:
                operations.append(("max", session.sync_session.get_transaction()))
            return await original_execute(statement, *args, **kwargs)

        async def complete(candidate, request):
            assert not session.in_transaction()
            assert operations == []
            return await original_complete(candidate, request)

        monkeypatch.setattr(session, "execute", execute)
        monkeypatch.setattr(adapter, "complete", complete)
        report = await StudyReportService(session, router).generate_report(_STUDY_ID)
        assert report.version == 1
        assert [operation for operation, _ in operations] == ["lock", "max"]
        assert operations[0][1] is not None
        assert operations[0][1] is operations[1][1]


async def test_unusable_synthesis_does_not_lock_allocate_or_persist_a_version(
    report_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch,
) -> None:
    router, adapter = _report_router("{}")
    statements: list[str] = []
    async with report_sessions() as session:
        original_execute = session.execute

        async def execute(statement, *args, **kwargs):
            statements.append(str(statement.compile(dialect=postgresql.dialect())))
            return await original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", execute)
        with pytest.raises(UnusableModelOutput):
            await StudyReportService(session, router).generate_report(_STUDY_ID)
        assert not session.in_transaction()
        assert all("FOR UPDATE" not in sql and "max(study_reports.version)" not in sql for sql in statements)
        assert len(adapter.requests) == 2
        assert adapter.requests[0].request_id != adapter.requests[1].request_id

    async with report_sessions() as session:
        assert list((await session.execute(select(StudyReports))).scalars()) == []


async def test_failed_report_write_rolls_back_study_and_releases_transaction(
    report_sessions: async_sessionmaker[AsyncSession],
) -> None:
    router, _ = _report_router()
    write_error = SQLAlchemyError("Fixture report write failure")

    def fail_report_write(session: Any, flush_context: Any, instances: Any) -> None:
        if any(isinstance(record, StudyReports) for record in session.new):
            raise write_error

    async with report_sessions() as session:
        event.listen(session.sync_session, "before_flush", fail_report_write)
        try:
            with pytest.raises(SQLAlchemyError) as failure:
                await StudyReportService(session, router).generate_report(_STUDY_ID)
            assert failure.value is write_error
            assert not session.in_transaction()
        finally:
            event.remove(session.sync_session, "before_flush", fail_report_write)

    async with report_sessions() as session:
        assert list((await session.execute(select(StudyReports))).scalars()) == []
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None
        assert study.status == "in_progress" and study.step == 4
        assert study.findings is None