import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base, Businesses
from bebshax.db.seed import seed_demo_data


@pytest.fixture
async def memory_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield sm
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_demo_data_skipped_when_demo_mode_false(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must not insert rows when demo_mode is False."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=False, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker)
    assert seeded is False

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count == 0


@pytest.mark.asyncio
async def test_seed_demo_data_runs_when_demo_mode_true(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must insert rows when demo_mode is True."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=True, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker)
    assert seeded is True

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count > 0


@pytest.mark.asyncio
async def test_seed_demo_data_runs_when_forced(monkeypatch, memory_sessionmaker):
    """H3 regression guard: seed_demo_data must insert rows when force=True regardless of demo_mode."""
    from bebshax.config import Settings
    monkeypatch.setattr("bebshax.config.get_settings", lambda: Settings(demo_mode=False, jwt_secret="test_secret_at_least_32_characters_long_12345"))

    seeded = await seed_demo_data(memory_sessionmaker, force=True)
    assert seeded is True

    async with memory_sessionmaker() as session:
        count = (await session.execute(select(func.count(Businesses.id)))).scalar_one_or_none() or 0
        assert count > 0
