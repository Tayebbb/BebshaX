"""Edge cases of the batched embedding call in the research run.

The batch refactor turned N per-source embed calls into one call over every
chunk. Two failure modes came with it: an empty batch (no sources) that some
backends reject, and a short vector list that made ``next()`` raise a bare
StopIteration inside a coroutine — surfacing as "coroutine raised StopIteration"
instead of a diagnosable error.
"""

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, Studies
from bebshax.research.search_provider import IllustrativeSampleProvider, SearchProvider
from bebshax.research.service import ResearchEngineService


class _NoResultsProvider(SearchProvider):
    async def search(self, queries, max_results_per_query: int = 4):
        return []


class _PlanAndQueriesLLM:
    """Answers the plan and query prompts; the claims prompt is never reached
    in these tests (no sources, or the embedding step fails first)."""

    async def complete(self, request):
        prompt = request.messages[-1].content.lower()
        if "research plan" in prompt:
            text = json.dumps(
                {
                    "target_market": ["students"],
                    "problem_areas": ["budgeting"],
                    "dataset_requirements": [{"category": "student_spending", "description": "d"}],
                    "summary": "s",
                }
            )
        else:
            text = json.dumps(["student meal budgets", "meal planning app alternatives", "student food spending"])

        class _R:
            provider = "fake"
            model = "stub"

        r = _R()
        r.text = text
        return r


_DOCS = [
    {"title": "Meal budgets", "url": "https://example.org/a", "content": "Students budget tightly for meals. " * 30},
    {"title": "Planning apps", "url": "https://example.org/b", "content": "Most planning apps are abandoned. " * 30},
]


class _RecordingVectorEngine:
    """Counts embed_texts calls and can return fewer vectors than requested."""

    def __init__(self, shortfall: int = 0) -> None:
        self.backend = type("_B", (), {"space": "test-space"})()
        self.calls: list[list[str]] = []
        self.shortfall = shortfall

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        keep = max(len(texts) - self.shortfall, 0)
        return [[0.0, 1.0] for _ in range(keep)]


async def _seed_study(session_maker, study_id: str) -> Studies:
    async with session_maker() as session:
        study = Studies(
            id=study_id,
            user_id="usr_embed_test",
            title="Embedding Batch Study",
            type="interviews",
            goal="demand_validation",
            prompt="A budget meal planning app for university students.",
            status="draft",
        )
        session.add(study)
        await session.commit()
    return study


async def _fresh_session_maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_no_sources_skips_the_embedding_call_entirely():
    session_maker = await _fresh_session_maker()
    await _seed_study(session_maker, "std_embed_empty")

    vector_engine = _RecordingVectorEngine()
    service = ResearchEngineService(
        search_provider=_NoResultsProvider(), vector_engine=vector_engine, llm_service=_PlanAndQueriesLLM()
    )

    async with session_maker() as session:
        study = await session.get(Studies, "std_embed_empty")
        run = await service.run_study_research(session, study, user_id="usr_embed_test")

    assert vector_engine.calls == [], "embed_texts must not be called with an empty batch"
    assert run.status == "completed", run.error_message
    assert run.source_count == 0
    # Honest markers: nothing was found and no hypothesis claims were substituted.
    summary = run.step_progress["summary"]
    assert summary["no_live_evidence"] is True and summary["claims_status"] == "no_evidence"
    assert run.claim_count == 0
    assert summary["evidence_provider"] == "_NoResultsProvider"


@pytest.mark.asyncio
async def test_short_embedding_batch_fails_with_a_diagnosable_error():
    session_maker = await _fresh_session_maker()
    await _seed_study(session_maker, "std_embed_short")

    vector_engine = _RecordingVectorEngine(shortfall=1)
    service = ResearchEngineService(
        search_provider=IllustrativeSampleProvider(_DOCS, allow_sample=True),
        vector_engine=vector_engine,
        llm_service=_PlanAndQueriesLLM(),
    )

    async with session_maker() as session:
        study = await session.get(Studies, "std_embed_short")
        run = await service.run_study_research(session, study, user_id="usr_embed_test")

    assert vector_engine.calls, "the sample provider should have produced chunks to embed"
    assert run.status == "failed"
    # The stored message names the failure class without leaking internals;
    # the full text goes to the server log.
    assert run.step_progress["summary"]["error_code"] == "run_failed"
    assert "RuntimeError" in (run.error_message or "")
    assert "StopIteration" not in (run.error_message or "")
