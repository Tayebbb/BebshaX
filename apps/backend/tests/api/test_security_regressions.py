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
    # A prefix check ("startswith") accepts these — origins must be compared parsed.
    with pytest.raises(ValueError):
        _assert_internal_redirect(f"{base}.evil.example/x", base)
    with pytest.raises(ValueError):
        _assert_internal_redirect("https://app.example.com.attacker.com/x", base)
    with pytest.raises(ValueError):
        _assert_internal_redirect("http://app.example.com/app", base)  # scheme downgrade


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


def test_demo_studies_are_readable_but_not_writable_by_anonymous_callers(client):
    """`is_demo` is a READ allowance. It must never let an unauthenticated
    caller overwrite the shared demo a judge is about to open."""
    import asyncio

    from bebshax.db.models import Studies

    async def seed():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            session.add(
                Studies(
                    id="std_demo_write_guard",
                    user_id="usr_system_holder",
                    title="Shared Demo",
                    status="in_progress",
                    is_demo=True,
                    prompt="Demo prompt",
                )
            )
            await session.commit()

    asyncio.run(seed())

    # Read stays open — the demo must remain browsable.
    assert client.get("/api/studies/std_demo_write_guard").status_code == 200

    # Every mutating path is closed to anonymous callers.
    assert client.patch(
        "/api/studies/std_demo_write_guard", json={"title": "Defaced"}
    ).status_code == 403
    assert client.post(
        "/api/studies/std_demo_write_guard/script/generate", json={"question_count": 3}
    ).status_code == 403
    assert client.post("/api/studies/std_demo_write_guard/research/run").status_code == 403
    assert client.delete("/api/studies/std_demo_write_guard").status_code == 403

    async def unchanged():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            row = await session.get(Studies, "std_demo_write_guard")
            assert row is not None and row.title == "Shared Demo"

    asyncio.run(unchanged())


def test_dataset_upload_enforces_the_shared_size_ceiling(client):
    """The 25 MB cap used on the URL-fetch path must also bound raw uploads."""
    from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES

    oversized = b"a,b\n" + b"1,2\n" * ((MAX_DATASET_FILE_SIZE_BYTES // 4) + 1)
    assert len(oversized) > MAX_DATASET_FILE_SIZE_BYTES
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("big.csv", oversized, "text/csv")},
        data={"name": "Oversized"},
    )
    assert resp.status_code == 413


def test_unauthenticated_llm_and_upload_endpoints_are_rate_limited():
    """These accept anonymous callers and either spend LLM budget or accept
    bulk bytes — each must carry an explicit limit like its siblings."""
    from bebshax.api.limiter import limiter

    for qualified in (
        "bebshax.api.copilot.generate_study_personas",
        "bebshax.api.datasets.upload_dataset_file",
        "bebshax.api.datasets.upload_study_dataset_file",
    ):
        assert limiter._route_limits.get(qualified), f"{qualified} must be rate-limited"


def test_signup_limits_survive_a_shared_nat_venue():
    """Every judge at an exhibition shares one socket IP; the account-creation
    limits are sized per-venue, while signin stays tight against brute force."""
    from bebshax.api.limiter import limiter

    def _limit_str(qualified: str) -> str:
        return str(limiter._route_limits[qualified][0].limit)

    assert "20 per 1 hour" in _limit_str("bebshax.api.auth.signup")
    assert "30 per 1 hour" in _limit_str("bebshax.api.auth.verify_email")
    assert "10 per 1 hour" in _limit_str("bebshax.api.auth.resend_verification")
    assert "5 per 1 minute" in _limit_str("bebshax.api.auth.signin")
    assert get_settings() is not None
