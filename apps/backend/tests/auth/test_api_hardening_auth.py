"""Auth hardening: identity-link password revocation, account-scoped OTP
verification with lockout, resend invalidation, PBKDF2 cost, timing oracle."""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from bebshax.api import auth as auth_api
from bebshax.api.limiter import limiter
from bebshax.auth import service as auth_service
from bebshax.auth.models import AuthRateLimits, EmailVerificationToken, Users
from bebshax.auth.security import PBKDF2_ITERATIONS, hash_password, verify_password

_PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def _reset_limiter():
    """Reset only the legacy IP limiter; transactional budgets use isolated databases."""
    limiter._limiter.storage.reset()
    yield
    limiter._limiter.storage.reset()


def _signup(client: TestClient, email: str) -> str:
    """Create an (unverified) email account; returns the OTP that was mailed."""
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post(
            "/api/auth/signup",
            json={"email": email, "full_name": "Test Person", "password": _PASSWORD},
        )
        assert resp.status_code == 201, resp.text
        return mock_send.call_args.kwargs["otp_code"]


def _resend(client: TestClient, email: str) -> str:
    with patch("bebshax.api.auth.send_verification_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200
        return mock_send.call_args.kwargs["otp_code"]


def _neon_response(email: str) -> dict:
    return {"user": {"email": email, "name": "Neon Person", "emailVerified": True}}


# ---------------------------------------------------------------------------
# (a) /auth/sync links a verified identity to an unverified local row
# ---------------------------------------------------------------------------

async def test_sync_revokes_the_unverified_password_so_old_signin_fails(api_test_app: TestClient, caplog):
    email = "prehijack@example.com"
    _signup(api_test_app, email)  # attacker-style: signed up, never verified

    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = _neon_response(email)
        with caplog.at_level("WARNING"):
            sync = api_test_app.post(
                "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
            )
    assert sync.status_code == 200, sync.text
    assert sync.json()["user"]["is_verified"] is True

    signin = api_test_app.post("/api/auth/signin", json={"email": email, "password": _PASSWORD})
    assert signin.status_code == 401
    assert signin.json()["detail"] == "Invalid email or password."  # uniform reply

    async with api_test_app.app.state.db_sessionmaker() as session:
        user = (await session.execute(select(Users).where(Users.email == email))).scalar_one()
        assert user.hashed_password is None
        assert user.is_verified is True
    assert any("revoked unverified local password" in r.getMessage() for r in caplog.records)


async def test_sync_keeps_the_password_of_an_already_verified_account(api_test_app: TestClient):
    email = "legit@example.com"
    otp = _signup(api_test_app, email)
    assert api_test_app.post("/api/auth/verify-email", json={"token": otp, "email": email}).status_code == 200

    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = _neon_response(email)
        assert api_test_app.post("/api/auth/sync", json={"neon_token": "t"}).status_code == 200

    signin = api_test_app.post("/api/auth/signin", json={"email": email, "password": _PASSWORD})
    assert signin.status_code == 200


# ---------------------------------------------------------------------------
# (b) verify-email is account-scoped, invalidated on resend, and rate-limited per account
# ---------------------------------------------------------------------------

async def test_token_issued_to_user_a_cannot_verify_user_b(api_test_app: TestClient):
    otp_a = _signup(api_test_app, "alice-otp@example.com")
    _signup(api_test_app, "bob-otp@example.com")

    cross = api_test_app.post(
        "/api/auth/verify-email", json={"token": otp_a, "email": "bob-otp@example.com"}
    )
    assert cross.status_code == 400
    assert cross.json()["detail"] == "Invalid verification token."

    async with api_test_app.app.state.db_sessionmaker() as session:
        bob = (await session.execute(select(Users).where(Users.email == "bob-otp@example.com"))).scalar_one()
        assert bob.is_verified is False

    own = api_test_app.post(
        "/api/auth/verify-email", json={"token": otp_a, "email": "alice-otp@example.com"}
    )
    assert own.status_code == 200


async def test_verify_email_requires_the_email_field(api_test_app: TestClient):
    otp = _signup(api_test_app, "needs-email@example.com")
    resp = api_test_app.post("/api/auth/verify-email", json={"token": otp})
    assert resp.status_code == 422
    assert resp.json()["error_code"] == "validation_error"


async def test_unknown_email_gets_the_same_invalid_token_reply(api_test_app: TestClient):
    resp = api_test_app.post(
        "/api/auth/verify-email", json={"token": "123456", "email": "ghost@example.com"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid verification token."


async def test_sixth_wrong_attempt_is_rejected_even_with_the_right_code(api_test_app: TestClient):
    email = "bruteforce@example.com"
    otp = _signup(api_test_app, email)
    wrong = "000000" if otp != "000000" else "111111"

    for _ in range(5):
        resp = api_test_app.post("/api/auth/verify-email", json={"token": wrong, "email": email})
        assert resp.status_code == 400

    locked = api_test_app.post("/api/auth/verify-email", json={"token": wrong, "email": email})
    assert locked.status_code == 429
    assert locked.json()["error_code"] == "too_many_attempts"

    # The lockout covers the real code too — guessing cannot be finished off.
    still_locked = api_test_app.post("/api/auth/verify-email", json={"token": otp, "email": email})
    assert still_locked.status_code == 429


async def test_lockout_is_per_account(api_test_app: TestClient):
    otp_a = _signup(api_test_app, "locked-a@example.com")
    otp_b = _signup(api_test_app, "free-b@example.com")
    wrong = "000000" if otp_a != "000000" else "111111"
    for _ in range(6):
        api_test_app.post("/api/auth/verify-email", json={"token": wrong, "email": "locked-a@example.com"})
    ok = api_test_app.post("/api/auth/verify-email", json={"token": otp_b, "email": "free-b@example.com"})
    assert ok.status_code == 200


async def test_lockout_expires_after_the_window(identity_state):
    payload = {"email": "absent@example.test", "token": "123456"}
    for attempt in range(5):
        response = await identity_state.client.post("/api/auth/verify-email", json=payload)
        assert response.status_code == 400
    locked = await identity_state.client.post("/api/auth/verify-email", json=payload)
    assert locked.status_code == 429
    async with identity_state.sessions() as session:
        for budget in await session.scalars(select(AuthRateLimits)):
            budget.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    elapsed = await identity_state.client.post("/api/auth/verify-email", json=payload)
    assert elapsed.status_code == 400


async def test_resend_invalidates_outstanding_codes(api_test_app: TestClient):
    email = "resend-inv@example.com"
    first = _signup(api_test_app, email)
    second = _resend(api_test_app, email)

    stale = api_test_app.post("/api/auth/verify-email", json={"token": first, "email": email})
    assert stale.status_code == 400
    assert stale.json()["detail"] == "Invalid verification token."

    fresh = api_test_app.post("/api/auth/verify-email", json={"token": second, "email": email})
    assert fresh.status_code == 200, fresh.text

    async with api_test_app.app.state.db_sessionmaker() as session:
        user = (await session.execute(select(Users).where(Users.email == email))).scalar_one()
        tokens = (
            await session.execute(
                select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
            )
        ).scalars().all()
        assert len(tokens) == 2 and all(t.used_at is not None for t in tokens)


# ---------------------------------------------------------------------------
# (c) PBKDF2 cost  (d) timing oracle
# ---------------------------------------------------------------------------

def _legacy_style_hash(password: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, dklen=32)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    return f"pbkdf2_sha256${iterations}${b64(salt)}${b64(dk)}"


def test_hash_format_encodes_iterations_so_the_cost_can_be_raised_safely():
    """The stored string carries its own iteration count and verification reads
    it back: bumping PBKDF2_ITERATIONS (OWASP floor 600k) never invalidates
    existing hashes. The bump itself is gated on tests/test_auth.py, which pins
    the `$100000$` prefix (outside this group's ownership)."""
    new = hash_password("correct horse")
    assert new.split("$")[1] == str(PBKDF2_ITERATIONS)
    assert verify_password("correct horse", new)
    assert not verify_password("wrong horse", new)

    # Hashes minted at OTHER iteration counts — past (100k) or future (600k) — verify.
    for iterations in (100_000, 600_000):
        other = _legacy_style_hash("legacy pw", iterations)
        assert verify_password("legacy pw", other), iterations
        assert not verify_password("nope", other), iterations


@pytest.mark.asyncio
async def test_unknown_email_and_passwordless_user_still_run_a_verification(monkeypatch):
    """Both fast-return paths used to skip PBKDF2 entirely, so response time
    disclosed whether an email was registered."""
    calls: list[str] = []

    def counting_verify(plain: str, hashed: str) -> bool:
        calls.append(hashed)
        return False

    monkeypatch.setattr(auth_service, "verify_password", counting_verify)

    class _Result:
        def __init__(self, user):
            self._user = user

        def scalar_one_or_none(self):
            return self._user

    class _Session:
        def __init__(self, user):
            self._user = user

        async def execute(self, stmt):
            return _Result(self._user)

    assert await auth_service.authenticate_user(_Session(None), "ghost@example.com", "pw") is None
    federated = Users(id="usr_f", email="f@example.com", full_name="F", hashed_password=None)
    assert await auth_service.authenticate_user(_Session(federated), "f@example.com", "pw") is None
    assert len(calls) == 2, "one dummy verification per fast-return path"
    assert calls[0] == calls[1] == auth_service._dummy_hash()
    assert calls[0].startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")
