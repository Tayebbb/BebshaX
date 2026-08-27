import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.db.models import Base, Businesses
from bebshax.db.seed import ensure_shared_tenant_users, seed_demo_data
from bebshax.tenancy import PUBLIC_OWNER_IDS


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


@pytest.mark.asyncio
async def test_ensure_shared_tenant_users_creates_all_public_owner_rows(memory_sessionmaker):
    """Every PUBLIC_OWNER_IDS id must get a users row so owner_id FKs (personas etc.) can insert."""
    await ensure_shared_tenant_users(memory_sessionmaker)

    async with memory_sessionmaker() as session:
        for owner_id in PUBLIC_OWNER_IDS:
            row = await session.get(Users, owner_id)
            assert row is not None, f"missing shared-tenant users row for {owner_id}"
            assert row.auth_provider == "system"


@pytest.mark.asyncio
async def test_ensure_shared_tenant_users_is_idempotent(memory_sessionmaker):
    """Running the bootstrap twice must not fail or duplicate rows."""
    await ensure_shared_tenant_users(memory_sessionmaker)
    await ensure_shared_tenant_users(memory_sessionmaker)

    async with memory_sessionmaker() as session:
        count = (
            await session.execute(
                select(func.count(Users.id)).where(Users.id.in_(PUBLIC_OWNER_IDS))
            )
        ).scalar_one()
        assert count == len(PUBLIC_OWNER_IDS)
