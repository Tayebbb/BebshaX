"""Regression tests for security fixes applied 2026-09-02.

Each test pins a hole that was found in a live audit, so it cannot silently reopen.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.config import Settings, get_settings
from bebshax.db.models import Base
from bebshax.main import app
from bebshax.payments.service import _assert_internal_redirect

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


@pytest.fixture
def client():
    return TestClient(app)


def test_user_enumeration_endpoint_is_gone(client):
    """GET /api/auth/users used to return every account's email to any logged-in user."""
    assert client.get("/api/auth/users").status_code == 404


def test_resend_verification_does_not_reveal_whether_email_is_registered(client):
    """Differing replies let an unauthenticated caller enumerate accounts."""
    unknown = client.post(
        "/api/auth/resend-verification",
        json={"email": "definitely-not-registered@example.com"},
    )
    assert unknown.status_code == 200
    assert unknown.json()["detail"] == "Verification email resent with 6-digit OTP code."


def test_checkout_redirect_must_stay_on_our_origin():
    """Stripe redirects the user's browser here after payment — an external URL is a phishing hop."""
    base = "https://app.example.com"
    _assert_internal_redirect(None, base)
    _assert_internal_redirect(f"{base}/app?checkout=success", base)
    with pytest.raises(ValueError):
        _assert_internal_redirect("https://phishing.example/steal", base)


def test_cors_regex_does_not_trust_arbitrary_hosting_subdomains():
    """A wildcard *.vercel.app/*.onrender.com regex plus credentials let anyone's
    deployment read a logged-in user's data."""
    regex = Settings(_env_file=None).cors_origin_regex
    assert "vercel" not in regex
    assert "onrender" not in regex


def test_jwt_secret_has_no_shipped_default():
    """A default signing key lets anyone forge tokens for a deployment that forgets to set it."""
    assert Settings.model_fields["jwt_secret"].default == ""
    with pytest.raises(ValueError):
        Settings(_env_file=None, jwt_secret="")


def test_security_headers_are_present(client):
    resp = client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_no_hardcoded_credentials_in_settings_defaults():
    """Live secrets were once shipped as Settings defaults in a public repo.

    Asserts the declared defaults, not a constructed instance: the developer's
    own .env legitimately supplies real values at runtime.
    """
    fields = Settings.model_fields
    assert fields["resend_api_key"].default is None
    assert fields["smtp_password"].default is None
    assert fields["smtp_username"].default is None
    assert "neon.tech" not in fields["database_url"].default
    assert "npg_" not in fields["database_url"].default
    assert get_settings() is not None
