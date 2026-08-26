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
