"""Integration tests for the autonomous evidence + dataset discovery run.

The pipeline is template-free: the plan, queries and claims come from the (fake)
model, evidence from an explicit test corpus, and datasets from a fake live
adapter whose content is imported through the real parse/profile pipeline.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.datasets.discovery.base_adapter import DatasetCandidateData
from bebshax.datasets.discovery.engine import DatasetDiscoveryEngine
from bebshax.db.models import Base, DatasetSources, Studies
from bebshax.main import app
from bebshax.research.service import ResearchEngineService

_CSV = "student_id,monthly_allowance,device\n" + "\n".join(
    f"s{i},{2500 + i * 100},{'phone' if i % 3 else 'laptop'}" for i in range(40)
)


class _FakeLiveAdapter:
    """Stands in for a live portal: one real-looking candidate whose tabular
    content was already fetched (as the World Bank adapter does)."""

    def __init__(self) -> None:
        self.received: dict = {}

    @property
    def source_name(self) -> str:
        return "fake-live-portal"

    async def search(self, queries, requirements, *, countries=None):
        self.received = {"queries": list(queries), "countries": list(countries or [])}
        return [
            DatasetCandidateData(
                source="fake-live-portal",
                external_id="portal#student-allowance-survey",
                name="Student monthly allowance survey — Dhaka undergraduates",
                description="Monthly allowance and primary device for 40 undergraduates in Dhaka.",
                url="https://portal.example.org/dataset/student-allowance-survey",
                download_url="https://portal.example.org/files/allowance.csv",
                publisher="Example Statistics Office",
                license="CC BY 4.0",
                format="csv",
                size_bytes=len(_CSV),
                tags=["students", "allowance", "budgets"],
                relevant_variables=["monthly_allowance", "device"],
                geographic_coverage="Dhaka, Bangladesh",
                category="student_spending",
                modified_at="2025-06-01T00:00:00",
                raw_data_content=_CSV,
            )
        ]


def _service(research_llm, sample_evidence_provider, adapter):
    llm, fake = research_llm()
    service = ResearchEngineService(
        llm_service=llm,
        search_provider=sample_evidence_provider,
        discovery_engine=DatasetDiscoveryEngine(adapters=[adapter]),
    )
    return service, fake


@pytest.mark.asyncio
async def test_full_autonomous_research_service_execution(tmp_path, monkeypatch, research_llm, sample_evidence_provider):
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path))
    from bebshax.config import get_settings

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    study_id = "std_auto_test_1"
    user_id = "usr_auto_test_1"
    adapter = _FakeLiveAdapter()

    async with session_maker() as session:
        user = Users(id=user_id, email="auto_test@example.com", full_name="Auto Tester", hashed_password="pw")
        study = Studies(
            id=study_id,
            user_id=user_id,
            title="AI Meal Planner for University Students",
            type="interviews",
            goal="demand_validation",
            prompt="I want to build an AI-powered meal planning app for university students in Bangladesh with monthly budget under 5000 BDT.",
            status="draft",
        )
        session.add_all([user, study])
        await session.commit()

        service, fake = _service(research_llm, sample_evidence_provider, adapter)
        run = await service.run_study_research(session, study, user_id=user_id)

        assert run.status == "completed", run.error_message
        assert run.current_step == "completed"
        assert run.query_count == 3
        assert run.source_count == 3
        assert run.claim_count == 3
        assert run.dataset_candidate_count == 1
        assert run.dataset_imported_count == 1

        summary = run.step_progress["summary"]
        assert summary["plan_source"] == "llm" and summary["queries_source"] == "llm"
        assert summary["claims_status"] == "extracted" and summary["no_live_evidence"] is False
        assert summary["target_countries"] == ["BGD"] and summary["no_datasets_found"] is False
        # The discovery adapter received the model-written queries and the plan's countries.
        assert adapter.received == {"queries": list(run.queries), "countries": ["BGD"]}

        plan = await service.get_research_plan(session, study_id)
        assert plan is not None and plan["source"] == "llm"
        assert plan["served_by"] == "pollinations/deepseek-r1"
        assert len(plan["target_market"]) > 0 and len(plan["dataset_requirements"]) > 0

        candidates = await service.list_dataset_candidates(session, study_id)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand["selection_status"] == "imported" and cand["imported_dataset_id"]
        assert cand["is_sample"] is False
        assert cand["relevance_score"] > 0.3 and cand["quality_score"] > 0.5
        imported = await session.get(DatasetSources, cand["imported_dataset_id"])
        assert imported.row_count == 40 and imported.column_count == 3
        assert imported.schema_metadata["is_sample"] is False
        # The categorical `device` column yields real observed segments.
        assert {s["name"] for s in imported.segments} == {"phone", "laptop"}
        assert sum(s["population_count"] for s in imported.segments) == 40
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_research_endpoints_and_idor_protection(tmp_path, monkeypatch, research_llm, sample_evidence_provider):
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path))
    from bebshax.config import get_settings

    get_settings.cache_clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.db_sessionmaker = session_maker

    owner_id = "usr_owner_123"
    other_user_id = "usr_intruder_456"
    study_id = "std_idor_research_1"

    async with session_maker() as session:
        user_owner = Users(id=owner_id, email="owner@example.com", full_name="Owner", hashed_password="pw")
        user_other = Users(id=other_user_id, email="intruder@example.com", full_name="Other", hashed_password="pw")
        study = Studies(
            id=study_id,
            user_id=owner_id,
            title="Student Study Habits in Bangladesh",
            type="interviews",
            prompt="Online learning habits and exam preparation tools in Bangladesh",
            status="ready",
        )
        session.add_all([user_owner, user_other, study])
        await session.commit()

        service, _ = _service(research_llm, sample_evidence_provider, _FakeLiveAdapter())
        run = await service.run_study_research(session, study, user_id=owner_id)
        assert run.status == "completed", run.error_message

    token_owner = create_access_token({"sub": owner_id, "email": "owner@example.com"})
    token_other = create_access_token({"sub": other_user_id, "email": "intruder@example.com"})
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    headers_other = {"Authorization": f"Bearer {token_other}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Intruder receives 404
        res_plan_other = await ac.get(f"/api/studies/{study_id}/research/plan", headers=headers_other)
        assert res_plan_other.status_code == 404

        res_cands_other = await ac.get(f"/api/studies/{study_id}/datasets/candidates", headers=headers_other)
        assert res_cands_other.status_code == 404

        # 2. Owner access succeeds
        res_plan_owner = await ac.get(f"/api/studies/{study_id}/research/plan", headers=headers_owner)
        assert res_plan_owner.status_code == 200
        plan_data = res_plan_owner.json()
        assert "target_market" in plan_data
        assert "dataset_requirements" in plan_data
        assert plan_data["source"] == "llm"

        res_cands_owner = await ac.get(f"/api/studies/{study_id}/datasets/candidates", headers=headers_owner)
        assert res_cands_owner.status_code == 200
        cands_data = res_cands_owner.json()
        assert len(cands_data) > 0
        assert "relevance_score" in cands_data[0]
        assert "selection_reason" in cands_data[0]
    get_settings.cache_clear()
