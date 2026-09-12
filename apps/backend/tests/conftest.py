"""Suite-wide fixtures. tests/ is not a package — helpers are shared from here."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bebshax_persona_ml.data import TrainingRecord

# B4 fail-fast: bebshax.config instantiates Settings at import time and exits
# without a JWT secret. Set a test-only value BEFORE any bebshax import below.
os.environ.setdefault("BEBSHAX_JWT_SECRET", "test-only-jwt-secret-not-for-production-0123456789")

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.testclient import TestClient

import bebshax.interview.orm  # noqa: F401
import bebshax.memory.orm  # noqa: F401
import bebshax.persona.orm  # noqa: F401
from bebshax.config import get_settings
from bebshax.db.models import Base
from bebshax.interview.engine import InterviewEngine
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.main import create_app
from bebshax.persona.evidence import EvidenceStore
from bebshax.persona.generation import PersonaEngine


@pytest.fixture
def ml_training_records() -> list["TrainingRecord"]:
    from bebshax_persona_ml.data import TrainingRecord

    occupations = [
        "Student", "Nurse", "Teacher", "Farmer", "Baker", "Courier",
        "Shop owner", "Software engineer", "Researcher", "Designer", "Chef", "Accountant",
    ]
    return [
        TrainingRecord(
            record_id=f"fixture-{index}",
            source="test-synthetic-usa",
            revision="fixture-v1",
            name=f"Test Person {index}" if index < 11 else None,
            age=21 + index * 3,
            occupation=occupation,
            education="College" if index < 11 else "",
            location="Austin, Texas, USA",
            description=f"A synthetic {occupation} balancing food delivery, work and study planning.",
            goals=["Save time planning meals and work", "Manage a limited budget"],
            pain_points=["Delivery costs and missed deadlines"],
            behaviors=["Uses a calendar to organize study and work"],
            documents={
                "professional_persona": f"A {occupation} managing work and study schedules.",
                "culinary_persona": "Plans meals with fresh food and a limited budget.",
            },
        )
        for index, occupation in enumerate(occupations)
    ]


@pytest.fixture
def ml_artifact(tmp_path: Path, ml_training_records: list["TrainingRecord"]) -> Path:
    from bebshax_persona_ml.model import ModelConfig, PersonaModel

    artifact_dir = tmp_path / "ml-persona-model"
    model = PersonaModel.fit(ml_training_records, ModelConfig(n_topics=2, seed=17, max_iter=1000))
    model.save(artifact_dir)
    return artifact_dir


_VALID_PERSONA_JSON = """
{
  "name": "Alex Mercer",
  "age": 31,
  "occupation": "Delivery Courier",
  "location": "Austin, TX",
  "income_range": "$40k - $50k",
  "education": "High School",
  "description": "Hardworking driver managing variable shift income.",
  "goals": [{"value": "Predictable weekly budget", "provenance": "SYNTHETIC", "evidence_ids": []}, {"value": "Save for maintenance", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "pain_points": [{"value": "Overdraft fees", "provenance": "SYNTHETIC", "evidence_ids": []}, {"value": "High fuel costs", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "needs": [{"value": "Instant payout tracking", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "motivations": [{"value": "Financial security", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "behaviors": [{"value": "Uses 3 apps", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "technology_usage": [{"value": "Mobile-only", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "purchase_behavior": [{"value": "Price-conscious", "provenance": "SYNTHETIC", "evidence_ids": []}],
  "personality_traits": [{"value": "Resourceful", "provenance": "SYNTHETIC", "evidence_ids": []}]
}
"""


@pytest.fixture
async def api_test_app(tmp_path, monkeypatch, ml_artifact):
    """Full app on sqlite with real local personas and a FakeAdapter-backed chat router."""
    from bebshax.llm.types import TaskType

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test_api_int.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    monkeypatch.setenv("BEBSHAX_ML_PERSONA_ARTIFACT_DIR", str(ml_artifact))
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BEBSHAX_EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("BEBSHAX_DEMO_MODE", "false")
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "development")
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    cand = RouteCandidate(provider="pollinations", model="deepseek-r1")
    fake_route = FakeRoute(
        candidate=cand,
        replies=[
            _VALID_PERSONA_JSON,
            "Speaking as Alex: That automated savings tool sounds great!",
            "Speaking as Alex: Another reply.",
        ],
        # Once the scripted replies are consumed the route keeps answering with a
        # valid persona document: the pipeline has no offline template, so any
        # multi-persona test needs a model that actually answers.
        reply=_VALID_PERSONA_JSON,
    )
    adapter = FakeAdapter(routes=[fake_route])
    original_complete = adapter.complete

    async def reject_persona_llm(candidate, llm_request):
        assert llm_request.task not in {
            TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT,
            TaskType.PERSONA_NARRATIVE, TaskType.CRITIC,
        }, "Production persona generation must never call an LLM"
        return await original_complete(candidate, llm_request)

    monkeypatch.setattr(adapter, "complete", reject_persona_llm)
    adapters = {
        "openrouter": FakeAdapter([]),
        "freellmpool": adapter,
        "pollinations": adapter,
    }

    monkeypatch.setattr("bebshax.main.build_default_adapters", lambda **kwargs: adapters)
    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        yield client
    get_settings.cache_clear()


async def seed_test_user(db_sessionmaker) -> str:
    """Insert a test user into the DB and return auth headers dict."""
    from bebshax.auth.models import Users
    from bebshax.auth.security import create_access_token

    user_id = "usr_test_fixture"
    async with db_sessionmaker() as session:
        existing = await session.get(Users, user_id)
        if not existing:
            session.add(Users(
                id=user_id,
                email="fixture@test.local",
                full_name="Test Fixture User",
                auth_provider="email",
                is_active=True,
                is_verified=True,
            ))
            await session.commit()
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth_headers(api_test_app):
    """Return auth headers for a seeded test user — use on write endpoints."""
    headers = await seed_test_user(api_test_app.app.state.db_sessionmaker)
    return headers


async def seed_developer_user(db_sessionmaker) -> dict[str, str]:
    """Insert a verified developer and return auth headers for diagnostics routes."""
    from bebshax.auth.models import Users
    from bebshax.auth.security import create_access_token

    user_id = "usr_test_developer"
    async with db_sessionmaker() as session:
        if await session.get(Users, user_id) is None:
            session.add(Users(
                id=user_id,
                email="developer@test.local",
                full_name="Test Developer",
                auth_provider="email",
                role="developer",
                is_active=True,
                is_verified=True,
            ))
            await session.commit()
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.fixture
async def developer_headers(api_test_app):
    """Developer-role headers: routes/status, routing/capacity and evaluation metrics
    are development-only, loopback-only and role-gated."""
    return await seed_developer_user(api_test_app.app.state.db_sessionmaker)


@pytest.fixture
async def ml_api_app(tmp_path: Path, ml_artifact: Path, monkeypatch, request):
    from bebshax.llm.types import TaskType

    artifact_state = getattr(request, "param", "ready")
    artifact_dir = ml_artifact
    if artifact_state == "missing":
        artifact_dir = tmp_path / "private-missing-artifact"
    elif artifact_state == "corrupt":
        (artifact_dir / "metadata.json").write_text("{}", encoding="utf-8")
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'ml_api.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
    monkeypatch.setenv("BEBSHAX_ML_PERSONA_ARTIFACT_DIR", str(artifact_dir))
    monkeypatch.setenv("BEBSHAX_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BEBSHAX_DEMO_MODE", "false")
    monkeypatch.setenv("BEBSHAX_EMBEDDING_BACKEND", "local")
    get_settings.cache_clear()

    engine = create_async_engine(db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="pollinations", model="deepseek-r1", context_window=100000),
        reply="I use a calendar to plan work and meals.",
    )])
    original_complete = adapter.complete

    async def reject_persona_llm(candidate, llm_request):
        assert llm_request.task not in {
            TaskType.PERSONA_GENERATION, TaskType.PERSONA_REFINEMENT,
            TaskType.PERSONA_NARRATIVE, TaskType.CRITIC,
        }, "Persona generation must never call an LLM"
        return await original_complete(candidate, llm_request)

    monkeypatch.setattr(adapter, "complete", reject_persona_llm)
    adapters = {"freellmpool": adapter, "openrouter": FakeAdapter([]), "pollinations": adapter}
    monkeypatch.setattr("bebshax.main.build_default_adapters", lambda **kwargs: adapters)
    app = create_app()
    app.state.ml_test_llm = adapter
    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def ml_auth_headers(ml_api_app) -> dict[str, str]:
    return await seed_test_user(ml_api_app.app.state.db_sessionmaker)


@pytest.fixture
async def ml_study(ml_api_app, ml_auth_headers) -> str:
    from bebshax.db.models import EvidenceClaims, MarketSegments, Studies

    study_id = "std_ml_contracts"
    async with ml_api_app.app.state.db_sessionmaker() as session:
        session.add(Studies(
            id=study_id, user_id="usr_test_fixture", title="Meal and Study Planner",
            prompt="Food delivery and work planning with a limited budget.",
            goal="demand_validation", target_audience="Students and workers in Dhaka",
            pricing_hypothesis="BDT 200 per month", status="active", step=2,
            findings={"market_summary": "Meal planning research_tail"},
            copilot_messages=[{"role": "user", "content": "Food delivery collected_context_tail"}],
        ))
        session.add_all([
            MarketSegments(
                id="seg_ml_young", study_id=study_id, user_id="usr_test_fixture",
                segmentation_run_id="srun_ml", name="Young planners", description="Student meal planning",
                population_percentage=60.0, population_count=60,
                characteristics={"demographics": {"age_range": [18, 30]}},
            ),
            MarketSegments(
                id="seg_ml_older", study_id=study_id, user_id="usr_test_fixture",
                segmentation_run_id="srun_ml", name="Working planners", description="Work and food planning",
                population_percentage=40.0, population_count=40,
                characteristics={"demographics": {"age_range": [31, 65]}},
            ),
        ])
        session.add_all([
            EvidenceClaims(
                id=f"ml_claim_{index}", study_id=study_id, user_id="usr_test_fixture",
                claim_text=f"Meal planning research claim {index}", category="problem", confidence=0.9,
                supporting_source_ids=["ml_test_research_source"],
            )
            for index in range(7)
        ])
        await session.commit()
    return study_id


@pytest.fixture
def ml_workflow_payload(ml_study: str) -> dict:
    return {
        "study_id": ml_study,
        "study_prompt": "Food delivery and work planning. Full business context_tail",
        "roles": [
            {"id": "role_first", "role": "Pilot", "description": "Meal delivery role_description_tail", "count": 2, "selected": True},
            {"id": "role_second", "role": "Artist", "description": "Work and study planning", "count": 2, "selected": True},
        ],
    }


@pytest.fixture
def ml_uploaded_dataset(ml_api_app, ml_auth_headers, ml_study) -> dict:
    response = ml_api_app.post(
        "/api/datasets/upload",
        files={"file": ("synthetic-planners.csv", (
            b"cohort,age,location\n"
            b"Student planners,21,Dhaka\nWorker planners,21,Dhaka\n"
            b"Student planners,30,Dhaka\nWorker planners,30,Dhaka\n"
            b"Student planners,54,Dhaka\nWorker planners,54,Dhaka\n"
        ), "text/csv")},
        data={"name": "Synthetic meal planning survey", "study_id": ml_study},
        headers=ml_auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Research-pipeline fakes (shared: tests/ is not a package). The pipeline is
# template-free, so tests need a "model" that answers the plan, query and claim
# prompts from the request it receives — never a fixed reply list.
# ---------------------------------------------------------------------------

_RESEARCH_PLAN_REPLY = {
    "business_idea": "x",
    "target_market": ["University students"],
    "problem_areas": ["Missed deadlines"],
    "behavioral_questions": ["How do students plan their week?"],
    "economic_questions": ["What monthly price is acceptable?"],
    "competition_questions": ["Which free tools are used today?"],
    "market_questions": ["How many students enrol yearly?"],
    "dataset_requirements": [
        {
            "category": "student_spending",
            "description": "budgets",
            "target_variables": ["allowance"],
            "geographic_scope": "Dhaka",
            "population_scope": "undergraduates",
        }
    ],
    "summary": "Validate demand among students.",
    "target_countries": ["BGD"],
}
_RESEARCH_QUERIES_REPLY = [
    "student study planner deadlines",
    "study planner subscription pricing students",
    "alternatives to study planner apps",
]


class TaskAwareFakeAdapter(FakeAdapter):
    """FakeAdapter whose reply depends on the task/prompt it receives: research
    plan -> queries -> claims (citing the chunk ids actually shown to it)."""

    def __init__(self, routes, *, plan_reply: dict | None = None, queries_reply: list[str] | None = None) -> None:
        super().__init__(routes)
        self.plan_reply = plan_reply or _RESEARCH_PLAN_REPLY
        self.queries_reply = queries_reply or _RESEARCH_QUERIES_REPLY

    async def complete(self, candidate, request):
        import json as _json

        from bebshax.llm.adapters.base import AdapterCompletion
        from bebshax.llm.types import TaskType, TokenUsage

        prompt = " ".join(m.content for m in request.messages)
        if request.task == TaskType.EVIDENCE_EXTRACTION:
            tokens = [tok.strip("()") for tok in prompt.split()]
            chunk_ids = [t for t in tokens if t.startswith("chk_")]
            src_ids = [t for t in tokens if t.startswith("src_")]
            text = _json.dumps(
                {"claims": [
                    {"claim_text": "Students miss deadlines while juggling several apps.", "status": "supported",
                     "category": "problem", "supporting_source_ids": src_ids[:1],
                     "supporting_chunk_ids": chunk_ids[:1], "rationale": "stated in chunk"},
                    {"claim_text": "A single planner would be adopted quickly.", "status": "inference",
                     "category": "behavior", "supporting_source_ids": [], "supporting_chunk_ids": [],
                     "rationale": "extrapolation"},
                    {"claim_text": "Students will pay any price for planners.", "status": "unsupported",
                     "category": "pricing", "supporting_source_ids": [], "supporting_chunk_ids": [],
                     "rationale": "contradicted by pricing chunk"},
                ]}
            )
        elif "research plan" in prompt.lower():
            text = _json.dumps(self.plan_reply)
        else:
            # json_mode requires a complete JSON object; the generator unwraps "queries".
            text = _json.dumps({"queries": self.queries_reply})
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        self.requests.append(request)
        return AdapterCompletion(text=text, usage=TokenUsage(), provider=candidate.provider, model=candidate.model)


@pytest.fixture
def research_llm():
    """(PoolRouter, TaskAwareFakeAdapter) wired under every pool adapter name."""

    def _build(app=None, **kwargs):
        cand = RouteCandidate(provider="pollinations", model="deepseek-r1")
        adapter = TaskAwareFakeAdapter(routes=[FakeRoute(candidate=cand)], **kwargs)
        adapters = {"freellmpool": adapter, "openrouter": FakeAdapter([]), "pollinations": adapter}
        sink = getattr(app.state, "provenance_sink", None) if app is not None else None
        return PoolRouter(adapters, on_provenance=sink.persist if sink is not None else None), adapter

    return _build


@pytest.fixture
def sample_evidence_provider():
    """Explicit test-only evidence corpus (never wired in production)."""
    from bebshax.research.search_provider import IllustrativeSampleProvider

    docs = [
        {
            "title": "Student planners survey",
            "url": "https://example.org/planners",
            "content": "University students report missing deadlines and juggling several apps for study planning. "
            "Many say a single planner with reminders would help them keep up with coursework.",
        },
        {
            "title": "Subscription pricing habits",
            "url": "https://example.org/pricing",
            "content": "Students prefer small monthly subscriptions paid through mobile wallets and abandon tools "
            "that cost more than a meal out per month.",
        },
        {
            "title": "Study tool alternatives",
            "url": "https://example.org/alternatives",
            "content": "Free calendar apps and paper notebooks remain the most common alternatives to dedicated "
            "study planners; switching costs are low.",
        },
    ]
    return IllustrativeSampleProvider(docs, allow_sample=True)

