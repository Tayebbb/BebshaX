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


# ---------------------------------------------------------------------------
# Study-scoped write gate: generic coverage
# ---------------------------------------------------------------------------

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _seed(rows) -> None:
    import asyncio

    async def run():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            session.add_all(rows)
            await session.commit()

    asyncio.run(run())


def _study_scoped_mutating_routes():
    """Every registered study-scoped route with a mutating method, read from the
    live OpenAPI schema so newly added endpoints are picked up automatically."""
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        if "{study_id}" not in path:
            continue
        methods = sorted(_MUTATING_METHODS & {m.upper() for m in operations})
        if methods:
            yield path, methods


def test_every_study_scoped_mutation_is_closed_to_anonymous_callers(client):
    """Walks the live route table so a newly added mutating endpoint is covered
    automatically. `is_demo` is a READ allowance: no anonymous POST/PUT/PATCH/
    DELETE against the shared demo study may ever succeed."""
    from bebshax.db.models import Studies

    study_id = "std_demo_route_walk"
    _seed([
        Studies(
            id=study_id,
            user_id="usr_system_holder",
            title="Shared Demo",
            status="in_progress",
            is_demo=True,
            prompt="Demo prompt",
        )
    ])

    routes = list(_study_scoped_mutating_routes())
    assert routes, "route walk found nothing — the filter is broken, not the app"

    failures = []
    for path, methods in routes:
        url = path.replace("{study_id}", study_id)
        # Any other path parameter only has to be well-formed; the gate runs first.
        while "{" in url:
            head, _, rest = url.partition("{")
            _, _, tail = rest.partition("}")
            url = f"{head}probe{tail}"
        for method in methods:
            if url.endswith("/upload"):
                resp = client.request(
                    method,
                    url,
                    files={"file": ("probe.csv", b"a,b\n1,2\n", "text/csv")},
                    data={"name": "probe"},
                )
            else:
                resp = client.request(method, url, json={})
            if 200 <= resp.status_code < 300:
                failures.append(f"{method} {url} -> {resp.status_code}")

    assert not failures, "anonymous callers reached study mutations: " + "; ".join(failures)


def test_demo_study_stays_readable_while_writes_are_closed(client):
    """The write gate must not cost the judge-facing demo its public read."""
    from bebshax.db.models import Studies

    _seed([
        Studies(
            id="std_demo_read_ok",
            user_id="usr_system_holder",
            title="Readable Demo",
            status="in_progress",
            is_demo=True,
        )
    ])
    assert client.get("/api/studies/std_demo_read_ok").status_code == 200
    assert client.get("/api/studies/std_demo_read_ok/reports").status_code == 200


def test_owner_keeps_full_write_access_to_their_own_study(client):
    """The tightened predicate must not lock legitimate owners out."""
    from bebshax.auth.models import Users
    from bebshax.auth.security import create_access_token
    from bebshax.db.models import Studies

    _seed([
        Users(
            id="usr_write_owner",
            email="write-owner@example.com",
            full_name="Write Owner",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        ),
        Studies(id="std_owned_write", user_id="usr_write_owner", title="Owned", status="draft"),
    ])
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'usr_write_owner'})}"}

    resp = client.patch("/api/studies/std_owned_write", json={"title": "Renamed"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"


# ---------------------------------------------------------------------------
# Cross-tenant IDOR via client-supplied persona id lists
# ---------------------------------------------------------------------------

def _seed_two_tenants(suffix: str):
    from bebshax.auth.models import Users
    from bebshax.auth.security import create_access_token
    from bebshax.db.models import Personas, Studies

    attacker, victim = f"usr_att_{suffix}", f"usr_vic_{suffix}"
    _seed([
        Users(
            id=attacker,
            email=f"attacker-{suffix}@example.com",
            full_name="Attacker",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        ),
        Users(
            id=victim,
            email=f"victim-{suffix}@example.com",
            full_name="Victim",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        ),
        Studies(id=f"std_att_{suffix}", user_id=attacker, title="Attacker Study", status="draft"),
        Studies(id=f"std_vic_{suffix}", user_id=victim, title="Victim Study", status="draft"),
        Personas(
            id=f"per_vic_{suffix}",
            study_id=f"std_vic_{suffix}",
            owner_id=victim,
            name="Victim Persona",
        ),
    ])
    return {"Authorization": f"Bearer {create_access_token({'sub': attacker})}"}


def test_behavioral_run_rejects_personas_from_another_study(client):
    """`target_persona_ids` was trusted verbatim, so an attacker could simulate
    a victim's persona and read the transcript back from their own run row."""
    from bebshax.behavioral.orm import BehavioralTests

    headers = _seed_two_tenants("bhv")
    _seed([
        BehavioralTests(
            id="bt_idor",
            study_id="std_att_bhv",
            user_id="usr_att_bhv",
            name="Pricing",
            test_type="pricing_test",
        )
    ])

    resp = client.post(
        "/api/studies/std_att_bhv/behavioral-tests/bt_idor/runs",
        json={
            "target_population_type": "selected_personas",
            "target_persona_ids": ["per_vic_bhv"],
            "scenario_text": "Would you buy this?",
        },
        headers=headers,
    )
    assert resp.status_code == 400


def test_batch_interview_rejects_personas_from_another_study(client):
    """The batch job resolved persona ids with no study filter at all."""
    headers = _seed_two_tenants("btch")

    resp = client.post(
        "/api/studies/std_att_btch/interviews/batch-run",
        json={"persona_ids": ["per_vic_btch"], "questions": ["Hello?"]},
        headers=headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Upload ceiling
# ---------------------------------------------------------------------------

def test_upload_reader_stops_before_buffering_the_whole_body():
    """The cap used to be applied after `await file.read()` had already put the
    entire multipart body in memory — a 25 MB limit with no OOM protection."""
    import asyncio

    from fastapi import HTTPException

    from bebshax.api.datasets import _read_upload_or_413
    from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES

    class _EndlessUpload:
        """Stands in for a client that keeps sending long past the ceiling."""

        def __init__(self) -> None:
            self.served = 0

        async def read(self, size: int = -1) -> bytes:
            self.served += size
            return b"x" * size

    upload = _EndlessUpload()
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(_read_upload_or_413(upload))
    assert excinfo.value.status_code == 413
    # Bounded overshoot: one chunk past the ceiling, not an unbounded body.
    assert upload.served <= MAX_DATASET_FILE_SIZE_BYTES + 64 * 1024


def test_oversized_content_length_is_rejected_before_the_body_is_read():
    """A declared Content-Length above the ceiling is refused up front."""
    import asyncio

    from fastapi import HTTPException

    from bebshax.api.datasets import _read_upload_or_413
    from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES

    class _NeverRead:
        async def read(self, size: int = -1) -> bytes:  # pragma: no cover - must not run
            raise AssertionError("body was read despite an oversized Content-Length")

    class _Request:
        headers = {"content-length": str(MAX_DATASET_FILE_SIZE_BYTES + 1)}

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(_read_upload_or_413(_NeverRead(), _Request()))
    assert excinfo.value.status_code == 413
