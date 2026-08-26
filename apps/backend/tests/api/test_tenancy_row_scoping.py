import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base, Businesses, Personas
from bebshax.main import app

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="module", autouse=True)
def _setup_app_db():
    import asyncio
    async def init():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_sessionmaker = sm
    app.state.sessionmaker = sm


client = TestClient(app)


@pytest.fixture(scope="module")
def setup_tenants():
    import asyncio
    async def init_data():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            # Create User A
            user_a = Users(
                id="usr_tenant_a",
                email="tenant_a@example.com",
                full_name="Tenant A",
                auth_provider="email",
                is_active=True,
                is_verified=True,
            )
            # Create User B
            user_b = Users(
                id="usr_tenant_b",
                email="tenant_b@example.com",
                full_name="Tenant B",
                auth_provider="email",
                is_active=True,
                is_verified=True,
            )
            # Create System Holder
            sys_user = Users(
                id="usr_system_holder",
                email="system@bebshax.internal",
                full_name="BebshaX System Data",
                auth_provider="system",
                is_active=True,
                is_verified=True,
            )
            session.add_all([user_a, user_b, sys_user])

            # Create Business for Tenant A
            biz_a = Businesses(
                id="biz_tenant_a",
                name="Business A",
                owner_id="usr_tenant_a",
            )
            # Create Business for Tenant B
            biz_b = Businesses(
                id="biz_tenant_b",
                name="Business B",
                owner_id="usr_tenant_b",
            )
            # Create System Demo Business
            biz_demo = Businesses(
                id="biz_demo_system",
                name="Demo Business",
                owner_id="usr_system_holder",
            )
            session.add_all([biz_a, biz_b, biz_demo])

            # Create Persona for Tenant B
            persona_b = Personas(
                id="per_tenant_b",
                name="Persona B",
                business_id="biz_tenant_b",
                owner_id="usr_tenant_b",
            )
            session.add(persona_b)
            await session.commit()
    asyncio.run(init_data())


def test_cross_tenant_business_listing_isolated(setup_tenants):
    token_a = create_access_token("usr_tenant_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    res_a = client.get("/api/businesses", headers=headers_a)
    assert res_a.status_code == 200
    biz_ids_a = [b["id"] for b in res_a.json()]
    assert "biz_tenant_a" in biz_ids_a
    assert "biz_demo_system" in biz_ids_a  # demo is visible
    assert "biz_tenant_b" not in biz_ids_a  # Tenant B business is NOT visible to Tenant A


def test_cross_tenant_persona_generation_blocked(setup_tenants):
    token_a = create_access_token("usr_tenant_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Tenant A attempts to generate a persona under Tenant B's business
    res = client.post(
        "/api/businesses/biz_tenant_b/personas",
        json={"hints": "test"},
        headers=headers_a,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "business not found"


def test_cross_tenant_persona_read_blocked(setup_tenants):
    token_a = create_access_token("usr_tenant_a")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Tenant A attempts to fetch Tenant B's private persona
    res = client.get("/api/personas/per_tenant_b", headers=headers_a)
    assert res.status_code == 404
    assert res.json()["detail"] == "persona not found"
