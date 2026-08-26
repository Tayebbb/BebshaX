"""Postgres/pgvector integration tests (run explicitly: pytest -m integration).

Requires: docker compose up -d db && alembic upgrade head.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.config import Settings
from bebshax.db.models import Businesses, Personas
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.embeddings import HashEmbedding
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryService

pytestmark = pytest.mark.integration

RELEVANT = [
    "asked how refunds work when a delivery arrives late",
    "complained about a late delivery and requested a refund",
    "wanted the refund policy explained for delayed orders",
    "asked whether late deliveries qualify for automatic refunds",
    "requested compensation after the delivery was two hours late",
]
NOISE = [f"talked about unrelated topic number {i} like gardening and chess" for i in range(15)]


@pytest.fixture
async def pg_env():
    url = Settings(_env_file=None).database_url
    engine = create_async_engine(url)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    business_id, persona_id = uuid.uuid4().hex, uuid.uuid4().hex
    async with maker() as session:
        session.add(Businesses(id=business_id, name="itest", description=None, owner_id="usr_system_holder"))
        session.add(Personas(id=persona_id, business_id=business_id, name="itest-persona", owner_id="usr_system_holder"))
        await session.commit()
    yield maker, persona_id
    async with maker() as session:  # cleanup
        from sqlalchemy import delete

        await session.execute(delete(MemoryItems).where(MemoryItems.persona_id == persona_id))
        await session.execute(delete(Personas).where(Personas.id == persona_id))
        await session.execute(delete(Businesses).where(Businesses.id == business_id))
        await session.commit()
    await engine.dispose()


async def test_store_20_memories_and_retrieve_expected_topk(pg_env) -> None:
    maker, persona_id = pg_env
    service = MemoryService(maker, HashEmbedding())
    for text in NOISE + RELEVANT:
        await service.remember(persona_id, text)

    results = await service.retrieve(persona_id, "refund policy for late delivery", k=5)
    assert len(results) == 5
    assert all(r.text in RELEVANT for r in results[:3]), [r.text for r in results]


async def test_reflection_produces_stored_summary_on_pg(pg_env) -> None:
    maker, persona_id = pg_env
    adapter = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="fake", model="m1"),
                replies=['{"insights": ["late deliveries are my biggest frustration"]}'],
            )
        ]
    )
    service = MemoryService(maker, HashEmbedding(), llm=SingleAdapterLLMService(adapter))
    for text in RELEVANT + NOISE[:5]:
        await service.remember(persona_id, text)

    stored = await service.reflect(persona_id)
    assert len(stored) == 1 and stored[0].kind == "reflection"
    results = await service.retrieve(persona_id, "biggest frustration with deliveries", k=3)
    assert any(r.kind == "reflection" for r in results)
