"""Memory test fixtures: sqlite engine with all tables + hash embeddings."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bebshax.memory.orm  # noqa: F401 — register memory_items on Base.metadata
import bebshax.persona.orm  # noqa: F401
from bebshax.db.models import Base
from bebshax.llm.adapters.embeddings import HashEmbedding


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_maker(async_engine):
    return sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def embeddings() -> HashEmbedding:
    return HashEmbedding()
