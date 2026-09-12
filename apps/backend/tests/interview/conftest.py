"""Interview test fixtures: sqlite with all tables, a stored persona, fake LLM."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import bebshax.interview.orm  # noqa: F401
import bebshax.memory.orm  # noqa: F401
import bebshax.persona.orm  # noqa: F401
import bebshax.personas.orm  # noqa: F401
from bebshax.db.models import Base
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.embeddings import HashEmbedding
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.memory.service import MemoryService
from bebshax.persona.schema import PersonaAttribute, PersonaProfile
from bebshax.persona.store import create_business, save_persona


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


@pytest_asyncio.fixture
async def stored_persona(session_maker) -> PersonaProfile:
    async with session_maker() as session:
        business = await create_business(session, "QuickBite", "food delivery in Dhaka", owner_id="usr_system_holder")
        profile = PersonaProfile(
            business_id=business.id,
            name="Rina Akter",
            age=24,
            occupation="university student",
            location="Dhaka, Bangladesh",
            income_range="student stipend",
            education="BSc in progress",
            description="Orders dinner online most weeknights; compares prices carefully.",
            attributes=[
                PersonaAttribute(key="goal", value="find affordable meal deals"),
                PersonaAttribute(key="pain_point", value="late deliveries"),
            ],
        )
        await save_persona(session, profile, owner_id="usr_system_holder")
        return profile


@pytest_asyncio.fixture
async def stored_persona_card(session_maker, stored_persona) -> str:
    """The identity card the engine actually renders: save_persona mirrors the
    profile onto the Personas row, and the engine prefers that row."""
    from bebshax.db.models import Personas
    from bebshax.interview.engine import build_identity_card

    async with session_maker() as session:
        row = await session.get(Personas, stored_persona.id)
    return build_identity_card(row)


def fake_llm(replies: list[str]):
    adapter = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="fake", model="m1"), replies=list(replies))]
    )
    return SingleAdapterLLMService(adapter), adapter


@pytest.fixture
def llm_factory():
    """Factory fixture: builds (LLMService, FakeAdapter) with scripted replies."""
    return fake_llm


@pytest.fixture
def memory_service(session_maker) -> MemoryService:
    return MemoryService(session_maker, HashEmbedding())
