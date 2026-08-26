import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base
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

VALID_SIGNUP_BASE = {"full_name": "Test User"}


def test_purely_numeric_password_rejected():
    """H8 regression guard: currently passes despite failing the UI's own claim."""
    response = client.post(
        "/api/auth/signup",
        json={**VALID_SIGNUP_BASE, "email": "numeric@example.com", "password": "12345678"},
    )
    assert response.status_code == 422


def test_purely_alphabetic_password_rejected():
    response = client.post(
        "/api/auth/signup",
        json={**VALID_SIGNUP_BASE, "email": "alpha@example.com", "password": "aaaaaaaa"},
    )
    assert response.status_code == 422


def test_alphanumeric_password_accepted():
    """Must not over-correct — a password matching the advertised rule still works."""
    response = client.post(
        "/api/auth/signup",
        json={**VALID_SIGNUP_BASE, "email": "alphanum@example.com", "password": "password1"},
    )
    assert response.status_code == 201


def test_short_password_still_rejected():
    """Confirm the existing min_length=8 rule wasn't accidentally weakened."""
    response = client.post(
        "/api/auth/signup",
        json={**VALID_SIGNUP_BASE, "email": "short@example.com", "password": "ab1"},
    )
    assert response.status_code == 422
