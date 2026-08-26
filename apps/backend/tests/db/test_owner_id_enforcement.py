import pytest
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.db.models import Base, Businesses, Personas
from bebshax.db.seed import seed_demo_data


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def sessionmaker_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    import asyncio
    async def init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return sm


@pytest.mark.asyncio
async def test_db_rejects_null_owner_id_on_business(db_session):
    """B6 Stage 2: SQLite/Postgres integrity error when owner_id is None on Businesses."""
    assert Businesses.__table__.c.owner_id.nullable is False
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        from sqlalchemy import text
        await db_session.execute(
            text("INSERT INTO businesses (id, name, owner_id) VALUES ('biz_null_owner', 'No Owner Biz', NULL)")
        )
        await db_session.commit()


@pytest.mark.asyncio
async def test_db_rejects_null_owner_id_on_persona(db_session):
    """B6 Stage 2: SQLite/Postgres integrity error when owner_id is None on Personas."""
    assert Personas.__table__.c.owner_id.nullable is False
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        from sqlalchemy import text
        await db_session.execute(
            text("INSERT INTO personas (id, name, owner_id) VALUES ('per_null_owner', 'No Owner Persona', NULL)")
        )
        await db_session.commit()



@pytest.mark.asyncio
async def test_system_holder_account_is_clearly_marked(sessionmaker_factory):
    """B6 Stage 2: usr_system_holder account is created and clearly tagged."""
    seeded = await seed_demo_data(sessionmaker_factory, force=True)
    assert seeded is True

    async with sessionmaker_factory() as session:
        system_user = await session.get(Users, "usr_system_holder")
        assert system_user is not None
        assert "system" in system_user.full_name.lower() or "system" in system_user.auth_provider.lower()


@pytest.mark.asyncio
async def test_seed_demo_data_sets_system_owner(sessionmaker_factory):
    """B6 Stage 2: Demo seeding attaches all businesses and personas to usr_system_holder."""
    seeded = await seed_demo_data(sessionmaker_factory, force=True)
    assert seeded is True

    async with sessionmaker_factory() as session:
        businesses = (await session.execute(select(Businesses))).scalars().all()
        assert len(businesses) > 0
        for b in businesses:
            assert b.owner_id == "usr_system_holder"

        personas = (await session.execute(select(Personas))).scalars().all()
        assert len(personas) > 0
        for p in personas:
            assert p.owner_id == "usr_system_holder"


@pytest.mark.asyncio
async def test_no_orphaned_rows_remain_after_backfill(sessionmaker_factory):
    """B6 Stage 2: Zero businesses or personas have NULL owner_id."""
    await seed_demo_data(sessionmaker_factory, force=True)

    async with sessionmaker_factory() as session:
        orphan_b = (await session.execute(select(Businesses).where(Businesses.owner_id.is_(None)))).scalars().all()
        assert len(orphan_b) == 0

        orphan_p = (await session.execute(select(Personas).where(Personas.owner_id.is_(None)))).scalars().all()
        assert len(orphan_p) == 0
