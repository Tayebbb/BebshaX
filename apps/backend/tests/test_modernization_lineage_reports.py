from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bebshax.behavioral.orm
import bebshax.interview.orm
from bebshax.db.models import Base, EvidenceClaims, Studies, StudyReports
from bebshax.jobs.orm import JobCheckpoints
from bebshax.jobs.runtime import JobRuntime
from bebshax.jobs.store import SQLJobStore
from bebshax.research.report_service import StudyReportService


@pytest.fixture
async def report_lineage(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'report_lineage.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=True)
    async with maker() as session:
        session.add(Studies(id="report_study", title="Original study", user_id="owner_one"))
        session.add(EvidenceClaims(id="report_claim", study_id="report_study", user_id="owner_one", claim_text="Original claim", status="inference"))
        await session.commit()
    try:
        yield maker
    finally:
        await engine.dispose()


async def test_report_preserves_captured_manifest_when_input_changes_during_model_call(report_lineage):
    maker = report_lineage

    async with maker() as session:
        async def complete(request):
            assert not session.in_transaction()
            async with maker() as other:
                claim = await other.get(EvidenceClaims, "report_claim")
                claim.claim_text = "Changed after capture"
                await other.commit()
            return SimpleNamespace(text=json.dumps({"executive_summary": "A specific synthetic inference from the supplied claim."}), provider="fake", model="fake")

        report = await StudyReportService(session, SimpleNamespace(complete=complete)).generate_report("report_study", user_id="owner_one")
        manifest = report.metrics["input_manifest"]
        assert manifest["consistency"] == "captured_inputs_not_database_version_freeze"
        assert manifest["evidence_claims"][0]["id"] == "report_claim"
        assert len(manifest["context_hash"]) == 64
        assert report.version == 1
    async with maker() as session:
        stored = (await session.scalars(select(StudyReports))).one()
        assert stored.metrics["input_manifest"] == manifest


async def test_report_checkpoint_links_artifact_and_manifest_atomically(report_lineage):
    maker = report_lineage
    store = SQLJobStore(maker)
    runtime = JobRuntime(store)

    async def complete(request):
        return SimpleNamespace(text=json.dumps({"executive_summary": "The captured evidence remains an unvalidated synthetic inference."}), provider="fake", model="fake")

    async def runner(job):
        async with maker() as session:
            report = await StudyReportService(session, SimpleNamespace(complete=complete)).generate_report("report_study", user_id="owner_one", job=job)
            job["result"] = {"id": report.id, "version": report.version}

    admitted = await runtime.start(kind="report_generation", scope_id="report_study", owner_id="owner_one", input_data={}, runner=runner)
    await runtime.drain()
    async with maker() as session:
        report = (await session.scalars(select(StudyReports))).one()
        checkpoint = (await session.scalars(select(JobCheckpoints))).one()
        assert checkpoint.status == "completed"
        assert checkpoint.result_refs["report_id"] == report.id
        assert checkpoint.result_refs["input_manifest"] == report.metrics["input_manifest"]
    job = await store.get(admitted["job_id"], kind="report_generation", scope_id="report_study", owner_id="owner_one")
    assert job["status"] == "completed"
    assert job["result_refs"]["report_id"] == job["result"]["id"]
    await runtime.shutdown()