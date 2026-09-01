"""Edge cases of the batched embedding call in the research run.

The batch refactor turned N per-source embed calls into one call over every
chunk. Two failure modes came with it: an empty batch (no sources) that some
backends reject, and a short vector list that made ``next()`` raise a bare
StopIteration inside a coroutine — surfacing as "coroutine raised StopIteration"
instead of a diagnosable error.
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, Studies
from bebshax.research.search_provider import SearchProvider
from bebshax.research.service import ResearchEngineService


class _NoResultsProvider(SearchProvider):
    async def search(self, queries, max_results_per_query: int = 4):
        return []


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
        search_provider=_NoResultsProvider(), vector_engine=vector_engine
    )

    async with session_maker() as session:
        study = await session.get(Studies, "std_embed_empty")
        run = await service.run_study_research(session, study, user_id="usr_embed_test")

    assert vector_engine.calls == [], "embed_texts must not be called with an empty batch"
    assert run.status == "completed"
    assert run.source_count == 0


@pytest.mark.asyncio
async def test_short_embedding_batch_fails_with_a_diagnosable_error():
    session_maker = await _fresh_session_maker()
    await _seed_study(session_maker, "std_embed_short")

    vector_engine = _RecordingVectorEngine(shortfall=1)
    service = ResearchEngineService(vector_engine=vector_engine)

    async with session_maker() as session:
        study = await session.get(Studies, "std_embed_short")
        run = await service.run_study_research(session, study, user_id="usr_embed_test")

    assert vector_engine.calls, "the curated provider should have produced chunks to embed"
    assert run.status == "failed"
    assert "vectors for" in (run.error_message or ""), (
        f"expected an explicit count mismatch message, got {run.error_message!r}"
    )
    assert "StopIteration" not in (run.error_message or "")
