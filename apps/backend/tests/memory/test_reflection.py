import pytest

from bebshax.llm import SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.memory.service import MemoryService


def _service_with_llm(session_maker, embeddings, replies: list[str]):
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=list(replies))]
    )
    return MemoryService(session_maker, embeddings, llm=SingleAdapterLLMService(adapter)), adapter


async def _seed_episodic(service: MemoryService, count: int) -> None:
    for i in range(count):
        await service.remember("p1", f"observation {i}: user asked about pricing tier {i % 3}")


async def test_reflection_stores_summary_items(session_maker, embeddings) -> None:
    service, adapter = _service_with_llm(
        session_maker,
        embeddings,
        ['{"insights": ["I care a lot about pricing tiers", "I compare options before deciding"]}'],
    )
    await _seed_episodic(service, 8)
    stored = await service.reflect("p1")
    assert len(stored) == 2
    assert all(item.kind == "reflection" and item.importance == 0.8 for item in stored)
    assert adapter.requests[-1].task == TaskType.MEMORY_SUMMARIZATION

    # reflections are now retrievable and boosted
    results = await service.retrieve("p1", "pricing", k=3)
    assert any(r.kind == "reflection" for r in results)


async def test_reflection_skips_below_threshold(session_maker, embeddings) -> None:
    service, adapter = _service_with_llm(session_maker, embeddings, ['{"insights": ["x"]}'])
    await _seed_episodic(service, 3)  # below min_episodic=8
    assert await service.reflect("p1") == []
    assert adapter.requests == []  # no LLM call wasted


async def test_unparseable_reflection_is_swallowed(session_maker, embeddings) -> None:
    service, _ = _service_with_llm(session_maker, embeddings, ["complete garbage, no json"])
    await _seed_episodic(service, 8)
    assert await service.reflect("p1") == []  # best-effort: never raises


async def test_reflect_without_llm_raises(session_maker, embeddings) -> None:
    service = MemoryService(session_maker, embeddings)
    with pytest.raises(ValueError):
        await service.reflect("p1")
