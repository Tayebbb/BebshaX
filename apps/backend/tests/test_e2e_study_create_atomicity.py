from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.api import studies
from bebshax.auth.models import Users
from bebshax.db.models import Base, Studies


@pytest.fixture
async def study_atomicity_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def study_atomicity_client(study_atomicity_db):
    app = FastAPI()
    app.include_router(studies.router, prefix="/api")
    async with study_atomicity_db() as seed_session:
        owner = Users(
            id="usr_atomic", email="atomic@example.test", full_name="Atomic Owner",
            auth_provider="email", is_active=True, is_verified=True,
        )
        seed_session.add(owner)
        await seed_session.commit()
    async with study_atomicity_db() as session:
        async def get_session() -> AsyncSession:
            return session

        async def get_current_user() -> Users:
            # Creation requires an authenticated owner; resolve it through the request session
            # so the handler's transaction shape matches production.
            return await session.get(Users, "usr_atomic")

        app.dependency_overrides[studies.get_session] = get_session
        app.dependency_overrides[studies.get_current_user] = get_current_user
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, session


@pytest.mark.asyncio
@pytest.mark.parametrize("expire_on_commit", [False, True])
async def test_study_create_returns_persisted_defaults(
    study_atomicity_client, study_atomicity_db, expire_on_commit: bool,
) -> None:
    client, session = study_atomicity_client
    session.sync_session.expire_on_commit = expire_on_commit

    response = await client.post(
        "/api/studies", json={"prompt": "A meal planner for students"},
    )

    assert response.status_code == 201
    body = response.json()
    async with study_atomicity_db() as verification:
        persisted = (await verification.execute(select(Studies))).scalar_one()
        assert body == studies._serialize_study(persisted)
        assert persisted.created_at is not None
        assert persisted.updated_at is not None
        assert body["created_at"] == persisted.created_at.isoformat()
        assert body["updated_at"] == persisted.updated_at.isoformat()
        assert body["script_meta"] == persisted.script_meta


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["refresh", "serialization", "commit"])
async def test_study_create_failure_rolls_back(
    study_atomicity_client, study_atomicity_db, monkeypatch, failure_stage: str,
) -> None:
    client, session = study_atomicity_client
    failure = RuntimeError(f"Injected {failure_stage} failure")
    rollback = AsyncMock(wraps=session.rollback)
    monkeypatch.setattr(session, "rollback", rollback)
    if failure_stage == "refresh":
        monkeypatch.setattr(session, "refresh", AsyncMock(side_effect=failure))
    elif failure_stage == "serialization":
        monkeypatch.setattr(studies, "_serialize_study", Mock(side_effect=failure))
    else:
        def fail_commit(sync_session) -> None:
            raise failure

        event.listen(session.sync_session, "before_commit", fail_commit)

    response = await client.post(
        "/api/studies", json={"prompt": "A meal planner for students"},
    )

    assert response.status_code == 500
    async with study_atomicity_db() as verification:
        persisted = (await verification.execute(select(Studies))).scalars().all()
        assert persisted == []
    rollback.assert_awaited_once()
    assert not session.in_transaction()