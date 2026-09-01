import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, bindparam, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base
from bebshax.auth.models import Users, EmailVerificationToken
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


def test_signup_creates_verification_token(client):
    """Stage 2: signing up creates an EmailVerificationToken and dispatches verification email."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={
                "email": "sarah_verify@example.com",
                "full_name": "Sarah Verify",
                "password": "Password123!",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["is_verified"] is False
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert args[0] == "sarah_verify@example.com"
        assert "token=" in args[1]


def test_signup_still_succeeds_if_email_send_fails(client):
    """Stage 2 fail-soft: provider error does not block account creation."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = False
        resp = client.post(
            "/api/auth/signup",
            json={
                "email": "fail_email@example.com",
                "full_name": "Fail Email User",
                "password": "Password123!",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["email"] == "fail_email@example.com"


def test_verify_email_with_valid_token_marks_user_verified(client):
    """Stage 3: /verify-email marks user verified and timestamps used_at."""
    # First sign up to get a real token
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        signup_resp = client.post(
            "/api/auth/signup",
            json={
                "email": "verify_me@example.com",
                "full_name": "Verify Me",
                "password": "Password123!",
            },
        )
        assert signup_resp.status_code == 201
        verification_url = mock_send.call_args[0][1]
        token_str = verification_url.split("token=")[1]

    verify_resp = client.post("/api/auth/verify-email", json={"token": token_str})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["detail"] == "Email verified successfully."

    # Signin should now reflect verified user
    signin_resp = client.post(
        "/api/auth/signin",
        json={"email": "verify_me@example.com", "password": "Password123!"},
    )
    assert signin_resp.status_code == 200
    assert signin_resp.json()["user"]["is_verified"] is True


def test_verify_email_rejects_already_used_token(client):
    """Stage 3: Token cannot be reused."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        client.post(
            "/api/auth/signup",
            json={
                "email": "reuse_token@example.com",
                "full_name": "Reuse Token",
                "password": "Password123!",
            },
        )
        token_str = mock_send.call_args[0][1].split("token=")[1]

    # First use succeeds
    client.post("/api/auth/verify-email", json={"token": token_str})

    # Second use fails
    resp = client.post("/api/auth/verify-email", json={"token": token_str})
    assert resp.status_code == 400
    assert "Token already used" in resp.json()["detail"]


def test_verify_email_rejects_invalid_token(client):
    """Stage 3: Unknown token returns 400."""
    resp = client.post("/api/auth/verify-email", json={"token": "nonexistent_token_123"})
    assert resp.status_code == 400
    assert "Invalid verification token" in resp.json()["detail"]


def test_resend_verification_dispatches_new_token(client):
    """Stage 3: /resend-verification generates new token for unverified user."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        client.post(
            "/api/auth/signup",
            json={
                "email": "resend_test@example.com",
                "full_name": "Resend Test",
                "password": "Password123!",
            },
        )
        assert mock_send.call_count == 1

        resend_resp = client.post(
            "/api/auth/resend-verification",
            json={"email": "resend_test@example.com"},
        )
        assert resend_resp.status_code == 200
        assert resend_resp.json()["detail"] == "Verification email resent with 6-digit OTP code."
        assert mock_send.call_count == 2


def test_verify_email_rejects_expired_token(client):
    """Stage 3: Expired token returns 400."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        client.post(
            "/api/auth/signup",
            json={
                "email": "expired_tok@example.com",
                "full_name": "Expired Tok",
                "password": "Password123!",
            },
        )
        token_str = mock_send.call_args[0][1].split("token=")[1]

    # Manually expire the token in db
    import asyncio
    async def expire():
        async with _engine.begin() as conn:
            from sqlalchemy import text
            # Bind through SQLAlchemy's DateTime type, exactly as the ORM column
            # does. Passing a raw datetime into text() instead hands it to the
            # sqlite3 default adapter, deprecated since Python 3.12 (L14).
            stmt = text(
                "UPDATE email_verification_tokens SET expires_at = :exp WHERE token = :t"
            ).bindparams(bindparam("exp", type_=DateTime(timezone=True)), bindparam("t"))
            await conn.execute(
                stmt,
                {"exp": datetime.now(timezone.utc) - timedelta(hours=1), "t": token_str},
            )
    asyncio.run(expire())

    resp = client.post("/api/auth/verify-email", json={"token": token_str})
    assert resp.status_code == 400
    assert "Verification link expired" in resp.json()["detail"]


def test_resend_verification_rate_limited(client):
    """Stage 3: Resend verification is rate-limited (10/hour — sized for a
    shared-NAT exhibition venue where every judge presents one socket IP)."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        client.post(
            "/api/auth/signup",
            json={
                "email": "throttle_resend@example.com",
                "full_name": "Throttle Resend",
                "password": "Password123!",
            },
        )
        # 10 resends allowed
        for _ in range(10):
            r = client.post("/api/auth/resend-verification", json={"email": "throttle_resend@example.com"})
            assert r.status_code == 200

        # 11th resend hits 429
        blocked = client.post("/api/auth/resend-verification", json={"email": "throttle_resend@example.com"})
        assert blocked.status_code == 429

