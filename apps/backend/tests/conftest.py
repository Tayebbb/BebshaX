"""Suite-wide fixtures. tests/ is not a package — helpers are shared from here."""

import os

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


@pytest.fixture(autouse=True)
def _hermetic_local_tier(monkeypatch):
    """Point OllamaAdapter at an unroutable port so no unit test ever touches a
    real daemon (connection refused is instant → adapter contributes no routes).
    Adapter-level tests inject their own mock clients and are unaffected."""
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:9")


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
async def api_test_app(tmp_path, monkeypatch):
    """Full app on sqlite with FakeAdapter-backed router — shared across API test modules."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'test_api_int.db'}"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)
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
    adapters = {
        "openrouter": adapter,
        "freellmpool": adapter,
        "ollama": adapter,
        "pollinations": adapter,
    }

    app = create_app()
    with TestClient(app) as client:
        llm_router = PoolRouter(adapters, on_provenance=app.state.provenance_sink)
        app.state.llm_adapters = adapters
        app.state.llm_router = llm_router
        app.state.llm_service = llm_router
        app.state.persona_engine = PersonaEngine(llm_router, EvidenceStore())
        app.state.interview_engine = InterviewEngine(
            llm_router, app.state.db_sessionmaker, memory=app.state.memory_service
        )
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
                [
                    {"claim_text": "Students miss deadlines while juggling several apps.", "status": "supported",
                     "category": "problem", "supporting_source_ids": src_ids[:1],
                     "supporting_chunk_ids": chunk_ids[:1], "rationale": "stated in chunk"},
                    {"claim_text": "A single planner would be adopted quickly.", "status": "inference",
                     "category": "behavior", "supporting_source_ids": [], "supporting_chunk_ids": [],
                     "rationale": "extrapolation"},
                    {"claim_text": "Students will pay any price for planners.", "status": "unsupported",
                     "category": "pricing", "supporting_source_ids": [], "supporting_chunk_ids": [],
                     "rationale": "contradicted by pricing chunk"},
                ]
            )
        elif "research plan" in prompt.lower():
            text = _json.dumps(self.plan_reply)
        else:
            text = _json.dumps(self.queries_reply)
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        self.requests.append(request)
        return AdapterCompletion(text=text, usage=TokenUsage(), provider=candidate.provider, model=candidate.model)


@pytest.fixture
def research_llm():
    """(PoolRouter, TaskAwareFakeAdapter) wired under every pool adapter name."""

    def _build(app=None, **kwargs):
        cand = RouteCandidate(provider="pollinations", model="deepseek-r1")
        adapter = TaskAwareFakeAdapter(routes=[FakeRoute(candidate=cand)], **kwargs)
        adapters = {name: adapter for name in ("openrouter", "freellmpool", "ollama", "pollinations")}
        sink = getattr(app.state, "provenance_sink", None) if app is not None else None
        return PoolRouter(adapters, on_provenance=sink), adapter

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

