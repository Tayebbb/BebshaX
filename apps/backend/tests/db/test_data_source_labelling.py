"""H3 piece 2 — cached vs live labelling.

The demo honesty requirement from docs/DEMO.md §4: content that came out of the
demo seeder must never present itself as live model output. These tests fail if
the label is dropped, defaulted the wrong way, or inferred from `demo_mode`
(which flips independently of the rows already in the table).
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import (
    DATA_SOURCE_CACHED,
    DATA_SOURCE_LIVE,
    Base,
    Personas,
)
from bebshax.persona.store import save_persona
from bebshax.persona.schema import PersonaProfile


@pytest.fixture
async def memory_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield sm
    await engine.dispose()


def _profile(pid: str) -> PersonaProfile:
    return PersonaProfile(
        id=pid,
        business_id="biz_test_01",
        name="Test Persona",
        age=34,
        occupation="Delivery courier",
        location="Dhaka",
        income_range="20k-30k BDT",
        education="Secondary",
        description="A test persona used only to assert data_source labelling.",
        status="ready",
        version=1,
        generation_model="test/model",
    )


@pytest.mark.asyncio
async def test_save_persona_defaults_to_live(memory_sessionmaker):
    """A persona saved without an explicit label is live — it came from inference."""
    async with memory_sessionmaker() as session:
        await save_persona(session, _profile("per_live_01"))
        await session.commit()

    async with memory_sessionmaker() as session:
        row = (await session.execute(
            select(Personas).where(Personas.id == "per_live_01")
        )).scalar_one()
        assert row.data_source == DATA_SOURCE_LIVE


@pytest.mark.asyncio
async def test_save_persona_records_cached_when_asked(memory_sessionmaker):
    """The seeder's explicit 'cached' must survive to the row."""
    async with memory_sessionmaker() as session:
        await save_persona(
            session, _profile("per_cached_01"), data_source=DATA_SOURCE_CACHED
        )
        await session.commit()

    async with memory_sessionmaker() as session:
        row = (await session.execute(
            select(Personas).where(Personas.id == "per_cached_01")
        )).scalar_one()
        assert row.data_source == DATA_SOURCE_CACHED


@pytest.mark.asyncio
async def test_seeded_personas_are_labelled_cached(monkeypatch, memory_sessionmaker):
    """The demo seeder must not produce rows that read as live output."""
    from bebshax.config import Settings
    monkeypatch.setattr(
        "bebshax.config.get_settings",
        lambda: Settings(
            demo_mode=True,
            jwt_secret="test_secret_at_least_32_characters_long_12345",
        ),
    )
    from bebshax.db.seed import seed_demo_data

    seeded = await seed_demo_data(memory_sessionmaker)
    assert seeded is True

    async with memory_sessionmaker() as session:
        rows = (await session.execute(select(Personas))).scalars().all()
        assert rows, "seeder produced no personas to check"
        assert all(r.data_source == DATA_SOURCE_CACHED for r in rows), (
            "seeded personas must be labelled cached, got: "
            f"{[(r.id, r.data_source) for r in rows]}"
        )


@pytest.mark.asyncio
async def test_serializer_exposes_data_source(memory_sessionmaker):
    """The label has to reach the API response, not just the table."""
    from bebshax.api.personas import _serialize_persona

    async with memory_sessionmaker() as session:
        await save_persona(
            session, _profile("per_ser_01"), data_source=DATA_SOURCE_CACHED
        )
        await session.commit()

    async with memory_sessionmaker() as session:
        row = (await session.execute(
            select(Personas).where(Personas.id == "per_ser_01")
        )).scalar_one()
        assert _serialize_persona(row)["data_source"] == DATA_SOURCE_CACHED
