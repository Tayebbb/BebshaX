"""Synthetic, database-backed auth fixtures with no app lifespan or external calls."""

from collections.abc import AsyncIterator
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from bebshax.api import auth as auth_api
from bebshax.api import limiter as rate_api
from bebshax.api.errors import RequestContextMiddleware, register_exception_handlers
from bebshax.auth import security
from bebshax.auth.models import Users
from bebshax.config import Settings
from bebshax.db.models import Base


@pytest.fixture(scope="session")
def identity_password_hash() -> str:
    return security.hash_password("Identity123!")


@pytest.fixture
async def api_test_app(tmp_path, monkeypatch) -> AsyncIterator[TestClient]:
    settings = Settings(
        _env_file=None, jwt_secret=secrets.token_urlsafe(48), environment="development",
        require_email_verification=True, rate_limit_storage_uri=None,
        rate_limit_trust_forwarded_for=False, resend_api_key=None,
        smtp_username=None, smtp_password=None,
    )
    for module in (auth_api, security, rate_api):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api.limiter, "enabled", False)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth-api.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.settings = settings
    app.include_router(auth_api.auth_router)
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        await engine.dispose()


@pytest.fixture
async def identity_state(tmp_path, monkeypatch, identity_password_hash) -> AsyncIterator[SimpleNamespace]:
    settings = Settings(
        _env_file=None, jwt_secret=secrets.token_urlsafe(48), environment="development",
        require_email_verification=True, frontend_base_url="https://app.example.test",
        cors_origins="https://app.example.test", rate_limit_storage_uri=None,
        rate_limit_trust_forwarded_for=False,
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(rate_api, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api.limiter, "enabled", False)
    verification_mail = AsyncMock(return_value=True)
    reset_mail = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_api, "send_verification_email", verification_mail)
    monkeypatch.setattr(auth_api, "send_password_reset_email", reset_mail)
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    engine = create_async_engine(database_url)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        session.add_all([
            Users(
                id=owner_id, email=email, full_name="Synthetic Owner",
                hashed_password=identity_password_hash, is_verified=True,
                is_active=True, auth_provider="email",
            )
            for owner_id, email in (
                ("usr_identity", "owner@example.test"), ("usr_other", "other@example.test")
            )
        ])
        await session.commit()
    app = FastAPI()
    app.state.db_sessionmaker = sessionmaker
    app.state.settings = settings
    app.include_router(auth_api.auth_router)

    @app.post("/optional-private")
    async def optional_private(user=Depends(auth_api.get_optional_current_user)):
        return {"owner_id": user.id if user else None}

    async with AsyncClient(transport=ASGITransport(app), base_url="https://api.example.test") as client:
        yield SimpleNamespace(
            app=app, client=client, sessions=sessionmaker, settings=settings,
            database_url=database_url, verification_mail=verification_mail, reset_mail=reset_mail,
        )
    await engine.dispose()