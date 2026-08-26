import logging
import pytest
from fastapi.testclient import TestClient

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from bebshax.db.models import Base
from bebshax.main import app, limiter

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


@pytest.fixture(autouse=True)
def _reset_limiter():
    try:
        limiter._limiter.storage.reset()
    except Exception:
        pass
    yield
    try:
        limiter._limiter.storage.reset()
    except Exception:
        pass




@pytest.fixture
def client():
    return TestClient(app)


def test_signin_rate_limited_after_threshold(client):
    """H7 regression guard: repeated failed signins from one IP must
    eventually return 429, not just keep returning 401 forever."""
    for _ in range(5):
        client.post(
            "/api/auth/signin",
            json={"email": "nonexistent@example.com", "password": "wrongpassword1"},
        )
    response = client.post(
        "/api/auth/signin",
        json={"email": "nonexistent@example.com", "password": "wrongpassword1"},
    )
    assert response.status_code == 429


def test_signin_not_rate_limited_on_first_attempt(client):
    """Must not over-correct — a normal user's first typo isn't blocked."""
    response = client.post(
        "/api/auth/signin",
        json={"email": "another-fresh-address@example.com", "password": "wrongpassword1"},
    )
    assert response.status_code in (401, 403)


def test_different_emails_from_same_ip_still_share_the_limit(client):
    """Confirms the limiter is keyed by IP, not by email — rotating target
    emails from one IP must not bypass the limit."""
    for i in range(5):
        client.post(
            "/api/auth/signin",
            json={"email": f"target{i}@example.com", "password": "wrongpassword1"},
        )
    response = client.post(
        "/api/auth/signin",
        json={"email": "yet-another-target@example.com", "password": "wrongpassword1"},
    )
    assert response.status_code == 429


def test_failed_attempt_is_logged_without_password(client, caplog):
    """Confirm the audit log captures email + IP, never the password itself."""
    with caplog.at_level(logging.WARNING, logger="bebshax.api.auth"):
        client.post(
            "/api/auth/signin",
            json={"email": "logtest@example.com", "password": "supersecretvalue123"},
        )
    log_text = caplog.text
    assert "logtest@example.com" in log_text
    assert "supersecretvalue123" not in log_text
