from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryService


@pytest.fixture
def service(session_maker, embeddings) -> MemoryService:
    return MemoryService(session_maker, embeddings)


async def test_remember_and_retrieve_orders_by_relevance(service) -> None:
    await service.remember("p1", "ordered a large cappuccino with oat milk at the coffee shop")
    await service.remember("p1", "complained that coffee delivery was late twice")
    await service.remember("p1", "watched a documentary about deep sea fish")

    results = await service.retrieve("p1", "late coffee delivery complaints", k=2)
    assert len(results) == 2
    assert "delivery was late" in results[0].text
    assert results[0].score is not None and results[0].score > results[1].score


async def test_retrieval_is_scoped_to_persona_and_space(service, session_maker) -> None:
    await service.remember("p1", "loves hiking on weekends")
    await service.remember("p2", "hates hiking entirely")
    # foreign-space row must be invisible even for the right persona
    async with session_maker() as session:
        await session.execute(
            update(MemoryItems)
            .where(MemoryItems.persona_id == "p2")
            .values(persona_id="p1", embedding_space="freellmpool:some-other-model")
        )
        await session.commit()

    results = await service.retrieve("p1", "hiking", k=10)
    assert len(results) == 1
    assert "loves hiking" in results[0].text


async def test_recency_breaks_ties_between_identical_memories(service, session_maker) -> None:
    # identical text under two kinds: same relevance, same importance → recency decides
    # (same kind + same text would dedupe into one row by design)
    old = await service.remember("p1", "asked about the premium plan price")
    new = await service.remember("p1", "asked about the premium plan price", kind="semantic")
    assert old.id != new.id
    async with session_maker() as session:
        await session.execute(
            update(MemoryItems)
            .where(MemoryItems.id == old.id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=30))
        )
        await session.commit()

    results = await service.retrieve("p1", "premium plan price", k=2)
    assert results[0].id == new.id


async def test_importance_boosts_reflections(service, session_maker) -> None:
    low = await service.remember("p1", "mentioned budget concerns", importance=0.1)
    high = await service.remember(
        "p1", "mentioned budget concerns", kind="reflection", importance=1.0
    )
    results = await service.retrieve("p1", "budget concerns", k=2)
    assert results[0].id == high.id and results[1].id == low.id


async def test_retrieve_updates_last_accessed(service, session_maker) -> None:
    await service.remember("p1", "prefers annual billing")
    await service.retrieve("p1", "billing", k=1)
    async with session_maker() as session:
        row = (await session.execute(select(MemoryItems))).scalars().first()
        assert row.last_accessed is not None


async def test_invalid_kind_rejected(service) -> None:
    with pytest.raises(ValueError):
        await service.remember("p1", "x", kind="prophetic")
