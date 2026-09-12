"""Email verification flow: OTP issued at signup, single-use, expiring, rate-limited.

Signup never returns a session; the account is `verification_required` until the
6-digit code is redeemed together with the email it was issued to.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import DateTime, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import EmailVerificationToken, Users
from bebshax.db.models import Base
from bebshax.main import app, limiter

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="module", autouse=True)
def _setup_app_db():
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


def _signup(client: TestClient, email: str) -> tuple[object, str | None]:
    """Sign up and return (response, otp_code delivered to the mailer)."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={"email": email, "full_name": "Test User", "password": "Password123!"},
        )
        code = mock_send.call_args.kwargs.get("otp_code") if mock_send.call_args else None
        return resp, code


def _verify(client: TestClient, email: str, code: str):
    return client.post("/api/auth/verify-email", json={"token": code, "email": email})


def test_signup_creates_verification_token(client):
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={"email": "sarah_verify@example.com", "full_name": "Sarah Verify", "password": "Password123!"},
        )
        assert resp.status_code == 201
        body = resp.json()
        # No session is minted before verification.
        assert body["verification_required"] is True
        assert body["access_token"] == "" and body["user"] is None
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "sarah_verify@example.com"
        assert args[1].endswith("/verify-email")
        code = kwargs["otp_code"]
        assert len(code) == 6 and code.isdigit()

    # The stored challenge is a keyed digest — the code itself is never persisted.
    async def stored():
        async with app.state.db_sessionmaker() as session:
            user = (await session.scalars(select(Users).where(Users.email == "sarah_verify@example.com"))).one()
            assert user.is_verified is False
            return (await session.scalars(select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == user.id,
            ))).all()
    records = asyncio.run(stored())
    assert len(records) == 1 and records[0].purpose == "email-verification"
    assert records[0].token != code and code not in records[0].token


def test_signup_still_succeeds_if_email_send_fails(client):
    """Fail-soft: provider error does not block account creation."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = False
        resp = client.post(
            "/api/auth/signup",
            json={"email": "fail_email@example.com", "full_name": "Fail Email User", "password": "Password123!"},
        )
        assert resp.status_code == 201
        assert resp.json()["verification_required"] is True
    signin = client.post("/api/auth/signin", json={"email": "fail_email@example.com", "password": "Password123!"})
    assert signin.status_code in (200, 403)
    if signin.status_code == 200:
        assert signin.json()["verification_required"] is True


def test_verify_email_with_valid_token_marks_user_verified(client):
    signup_resp, code = _signup(client, "verify_me@example.com")
    assert signup_resp.status_code == 201 and code

    verify_resp = _verify(client, "verify_me@example.com", code)
    assert verify_resp.status_code == 200, verify_resp.text
    body = verify_resp.json()
    assert body["detail"] == "Email verified successfully."
    assert body["user"]["is_verified"] is True and body["access_token"]

    signin_resp = client.post(
        "/api/auth/signin", json={"email": "verify_me@example.com", "password": "Password123!"},
    )
    assert signin_resp.status_code == 200
    assert signin_resp.json()["user"]["is_verified"] is True


def test_verify_email_requires_matching_account(client):
    """A code is bound to the account it was issued to."""
    _, code = _signup(client, "bound_owner@example.com")
    _signup(client, "bound_other@example.com")
    assert code
    resp = _verify(client, "bound_other@example.com", code)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid verification token."


def test_verify_email_rejects_already_used_token(client):
    _, code = _signup(client, "reuse_token@example.com")
    assert code
    assert _verify(client, "reuse_token@example.com", code).status_code == 200
    resp = _verify(client, "reuse_token@example.com", code)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid verification token."


def test_verify_email_rejects_invalid_token(client):
    # Wrong shape is rejected by validation; a well-formed unknown code by the flow.
    malformed = client.post(
        "/api/auth/verify-email", json={"token": "nonexistent_token_123", "email": "nobody-here@example.com"},
    )
    assert malformed.status_code == 422
    resp = _verify(client, "nobody-here@example.com", "123456")
    assert resp.status_code == 400
    assert "Invalid verification token" in resp.json()["detail"]


def test_verify_email_locks_after_repeated_wrong_codes(client):
    _, code = _signup(client, "brute_force@example.com")
    assert code
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert _verify(client, "brute_force@example.com", wrong).status_code in (400, 429)
    # The challenge is burnt after OTP_MAX_ATTEMPTS: even the right code no longer works.
    assert _verify(client, "brute_force@example.com", code).status_code in (400, 429)


def test_resend_verification_dispatches_new_token(client):
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        client.post(
            "/api/auth/signup",
            json={"email": "resend_test@example.com", "full_name": "Resend Test", "password": "Password123!"},
        )
        assert mock_send.call_count == 1
        first_code = mock_send.call_args.kwargs["otp_code"]

        resend_resp = client.post("/api/auth/resend-verification", json={"email": "resend_test@example.com"})
        assert resend_resp.status_code == 200
        assert resend_resp.json()["detail"] == "Verification email resent with 6-digit OTP code."
        assert mock_send.call_count == 2
        second_code = mock_send.call_args.kwargs["otp_code"]

    # Re-issuing supersedes the earlier challenge.
    assert _verify(client, "resend_test@example.com", first_code).status_code == 400
    assert _verify(client, "resend_test@example.com", second_code).status_code == 200


def test_resend_verification_does_not_reveal_unknown_accounts(client):
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        resp = client.post("/api/auth/resend-verification", json={"email": "ghost@example.com"})
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Verification email resent with 6-digit OTP code."
        mock_send.assert_not_called()


def test_verify_email_rejects_expired_token(client):
    _, code = _signup(client, "expired_tok@example.com")
    assert code

    async def expire():
        async with _engine.begin() as conn:
            stmt = text(
                "UPDATE email_verification_tokens SET expires_at = :exp WHERE user_id IN "
                "(SELECT id FROM users WHERE email = :email)"
            ).bindparams(bindparam("exp", type_=DateTime(timezone=True)), bindparam("email"))
            await conn.execute(
                stmt, {"exp": datetime.now(timezone.utc) - timedelta(hours=1), "email": "expired_tok@example.com"},
            )
    asyncio.run(expire())

    resp = _verify(client, "expired_tok@example.com", code)
    assert resp.status_code == 400
    assert "Invalid verification token" in resp.json()["detail"]


def test_resend_verification_rate_limited(client):
    """Per-account resend budget (5 per 15 min) closes before the per-IP one."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock):
        client.post(
            "/api/auth/signup",
            json={"email": "throttle_resend@example.com", "full_name": "Throttle Resend", "password": "Password123!"},
        )
        for _ in range(5):
            r = client.post("/api/auth/resend-verification", json={"email": "throttle_resend@example.com"})
            assert r.status_code == 200

        blocked = client.post("/api/auth/resend-verification", json={"email": "throttle_resend@example.com"})
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After")
