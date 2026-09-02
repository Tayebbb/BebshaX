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


def _seeded_user_headers(user_id: str) -> dict[str, str]:
    """Insert a user and return its bearer header — dataset ingestion is
    authenticated now, so size/shape probes need a real token."""
    import asyncio

    from bebshax.auth.models import Users
    from bebshax.auth.security import create_access_token

    async def run():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            if await session.get(Users, user_id) is None:
                session.add(
                    Users(
                        id=user_id,
                        email=f"{user_id}@example.com",
                        full_name=user_id,
                        auth_provider="email",
                        is_active=True,
                        is_verified=True,
                    )
                )
                await session.commit()

    asyncio.run(run())
    return {"Authorization": f"Bearer {create_access_token({'sub': user_id})}"}


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


def test_dataset_ingestion_requires_authentication(client):
    """Anonymous uploads were stamped with the shared anonymous tenant, whose
    rows are world-readable — one visitor's file became every visitor's."""
    anon_upload = client.post(
        "/api/datasets/upload",
        files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")},
        data={"name": "Anon"},
    )
    assert anon_upload.status_code == 401
    anon_url = client.post(
        "/api/datasets/url",
        json={"url": "https://example.invalid/x.csv", "name": "Anon"},
    )
    assert anon_url.status_code == 401


def test_unauthenticated_llm_spend_endpoints_require_a_token(client):
    """suggest-roles makes a real LLM call; anonymous access was free spend."""
    assert client.post(
        "/api/study/suggest-roles", json={"study_prompt": "probe"}
    ).status_code == 401


def test_dataset_upload_enforces_the_shared_size_ceiling(client):
    """The 25 MB cap used on the URL-fetch path must also bound raw uploads."""
    from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES

    oversized = b"a,b\n" + b"1,2\n" * ((MAX_DATASET_FILE_SIZE_BYTES // 4) + 1)
    assert len(oversized) > MAX_DATASET_FILE_SIZE_BYTES
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("big.csv", oversized, "text/csv")},
        data={"name": "Oversized"},
        headers=_seeded_user_headers("usr_size_ceiling"),
    )
    assert resp.status_code == 413


def test_unauthenticated_llm_and_upload_endpoints_are_rate_limited():
    """These either spend LLM budget or accept bulk bytes / make outbound
    fetches — each must carry an explicit limit like its siblings."""
    from bebshax.api.limiter import limiter

    def _limit_str(qualified: str) -> str:
        return str(limiter._route_limits[qualified][0].limit)

    for qualified in (
        "bebshax.api.copilot.generate_study_personas",
        "bebshax.api.datasets.upload_dataset_file",
        "bebshax.api.datasets.upload_study_dataset_file",
    ):
        assert limiter._route_limits.get(qualified), f"{qualified} must be rate-limited"

    # URL ingestion performs an outbound fetch, so it is at least as expensive
    # as an upload and is pinned to the same budget.
    assert "10 per 1 hour" in _limit_str("bebshax.api.datasets.ingest_dataset_url")
    assert "10 per 1 hour" in _limit_str("bebshax.api.datasets.ingest_study_dataset_url")
    assert "10 per 1 hour" in _limit_str("bebshax.api.datasets.upload_dataset_file")
    assert "10 per 1 hour" in _limit_str("bebshax.api.datasets.upload_study_dataset_file")
    assert "30 per 1 minute" in _limit_str("bebshax.api.copilot.suggest_persona_roles")


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

# A gate must answer with an auth/authorisation verdict. 422 means the probe
# never reached the gate (schema validation rejected it first), which is how a
# wide-open route used to sneak through a "not 2xx" assertion.
_REFUSAL_CODES = {401, 403, 404}


def _seed(rows) -> None:
    import asyncio

    async def run():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            session.add_all(rows)
            await session.commit()

    asyncio.run(run())


def _components() -> dict:
    return app.openapi().get("components", {}).get("schemas", {})


def _resolve(schema: dict, components: dict) -> dict:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _first_pattern_alternative(pattern: str) -> str:
    body = pattern.strip("^$")
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    return body.split("|")[0]


def _example_for(schema: dict, components: dict, name: str = ""):
    """Smallest value that satisfies a schema, so probes are schema-VALID and
    actually reach the endpoint's authorisation gate."""
    schema = _resolve(schema, components)
    if schema.get("enum"):
        return schema["enum"][0]
    if schema.get("const") is not None:
        return schema["const"]
    for key in ("anyOf", "oneOf"):
        for sub in schema.get(key, []):
            if _resolve(sub, components).get("type") != "null":
                return _example_for(sub, components, name)
    kind = schema.get("type")
    if kind == "array":
        item = schema.get("items", {"type": "string"})
        return [_example_for(item, components, name) for _ in range(max(1, schema.get("minItems", 1)))]
    if kind == "object":
        return _object_example(schema, components)
    if kind == "integer":
        return int(schema.get("minimum", 1)) or 1
    if kind == "number":
        return float(schema.get("minimum", 1) or 1)
    if kind == "boolean":
        return False
    if schema.get("pattern"):
        return _first_pattern_alternative(schema["pattern"])
    if schema.get("format") in {"uri", "url"} or name.endswith("url"):
        return "https://example.invalid/probe.csv"
    return "probe" * max(1, -(-int(schema.get("minLength", 1)) // 5))


def _object_example(schema: dict, components: dict) -> dict:
    schema = _resolve(schema, components)
    props = schema.get("properties", {})
    return {
        field: _example_for(sub, components, field)
        for field, sub in props.items()
        if field in set(schema.get("required", []))
    }


def _probe_payload(operation: dict, overrides: dict) -> dict:
    """kwargs for TestClient.request that satisfy the operation's schema."""
    body = operation.get("requestBody")
    if not body:
        return {}
    components = _components()
    content = body["content"]
    if "application/json" in content:
        payload = _object_example(content["application/json"]["schema"], components)
        payload.update(overrides)
        return {"json": payload}
    if "multipart/form-data" in content:
        media = _resolve(content["multipart/form-data"]["schema"], components)
        required = set(media.get("required", []))
        data, files = {}, {}
        for field, sub in media.get("properties", {}).items():
            resolved = _resolve(sub, components)
            is_file = resolved.get("format") == "binary" or "contentMediaType" in resolved
            if is_file:
                files[field] = ("probe.csv", b"a,b\n1,2\n", "text/csv")
            elif field in required:
                data[field] = _example_for(sub, components, field)
        data.update({k: v for k, v in overrides.items() if v is not None})
        return {"data": data, "files": files or None}
    return {}


def _study_scoped_mutating_routes():
    """Every registered study-scoped route with a mutating method, read from the
    live OpenAPI schema so newly added endpoints are picked up automatically."""
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        if "{study_id}" not in path:
            continue
        for method, operation in operations.items():
            if method.upper() in _MUTATING_METHODS:
                yield path, method.upper(), operation


def _body_study_id_routes():
    """Routes that take a study id in the BODY/FORM instead of the path. These
    are invisible to a `{study_id}`-path walk, which is how an unauthenticated
    cross-tenant dataset write survived the previous version of this test."""
    schema = app.openapi()
    components = _components()
    for path, operations in schema["paths"].items():
        if "{study_id}" in path:
            continue
        for method, operation in operations.items():
            if method.upper() not in _MUTATING_METHODS:
                continue
            body = operation.get("requestBody")
            if not body:
                continue
            for media in body["content"].values():
                if "study_id" in _resolve(media["schema"], components).get("properties", {}):
                    yield path, method.upper(), operation
                    break


def _fill_path(path: str, study_id: str) -> str:
    url = path.replace("{study_id}", study_id)
    while "{" in url:
        head, _, rest = url.partition("{")
        _, _, tail = rest.partition("}")
        url = f"{head}probe{tail}"
    return url


def _refusals(client, routes, study_id: str, *, headers=None, in_body=False) -> list[str]:
    failures = []
    for path, method, operation in routes:
        url = _fill_path(path, study_id)
        overrides = {"study_id": study_id} if in_body else {}
        kwargs = _probe_payload(operation, overrides)
        resp = client.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 422:
            failures.append(
                f"{method} {url} -> 422 (probe never reached the gate; a hole here would be invisible)"
            )
        elif resp.status_code not in _REFUSAL_CODES:
            failures.append(f"{method} {url} -> {resp.status_code}")
    return failures


def test_every_study_scoped_mutation_is_closed_to_anonymous_callers(client):
    """Walks the live route table so a newly added mutating endpoint is covered
    automatically. `is_demo` is a READ allowance: no anonymous POST/PUT/PATCH/
    DELETE against the shared demo study may ever succeed. Probes carry
    schema-valid bodies and must be answered with 401/403/404 — a 422 is a
    failure, not a pass."""
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

    failures = _refusals(client, routes, study_id)
    assert not failures, "anonymous callers reached study mutations: " + "; ".join(failures)


def test_body_supplied_study_id_routes_enforce_the_same_gate(client):
    """`POST /datasets/upload` and friends take the study id in the body, so the
    path-based walk never saw them — and one of them was a fully
    unauthenticated cross-tenant write."""
    from bebshax.auth.models import Users
    from bebshax.db.models import Studies

    _seed([
        Users(
            id="usr_body_victim",
            email="body-victim@example.com",
            full_name="Body Victim",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        ),
        Studies(id="std_body_victim", user_id="usr_body_victim", title="Victim", status="draft"),
    ])

    routes = list(_body_study_id_routes())
    assert routes, "no body-supplied study_id routes found — the discovery filter is broken"

    failures = _refusals(client, routes, "std_body_victim", in_body=True)
    assert not failures, "body-supplied study_id bypassed the gate: " + "; ".join(failures)



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


def test_readable_demo_mutations_get_an_honest_403_not_a_false_404(client):
    """A caller who is READING the demo and clicks a write action must be told
    the study is read-only — "study not found" is factually wrong for a study
    on their screen. Studies the caller cannot read at all stay 404 so
    existence never leaks."""
    from bebshax.auth.models import Users
    from bebshax.db.models import Studies

    _seed([
        Users(
            id="usr_ro_owner",
            email="ro-owner@example.com",
            full_name="Hidden Owner",
            hashed_password="hash",
            is_active=True,
            is_verified=True,
        ),
        Studies(
            id="std_demo_ro",
            user_id="usr_system_holder",
            title="Read-Only Demo",
            status="completed",
            is_demo=True,
        ),
        Studies(id="std_hidden_ro", user_id="usr_ro_owner", title="Hidden", status="draft"),
    ])
    headers = _seeded_user_headers("usr_ro_reader")

    # Copilot generate-personas: the judge's backtrack-to-step-2 path.
    demo_gen = client.post(
        "/api/study/generate-personas",
        json={"study_id": "std_demo_ro", "study_prompt": "probe", "roles": []},
        headers=headers,
    )
    assert demo_gen.status_code == 403
    assert "read-only example study" in demo_gen.json()["detail"]

    # Study-scoped write gates converted to the same pattern.
    demo_run = client.post(
        "/api/studies/std_demo_ro/personas/generate",
        json={"target_count": 1, "distribution_strategy": "equal"},
        headers=headers,
    )
    assert demo_run.status_code == 403
    assert "read-only example study" in demo_run.json()["detail"]

    demo_research = client.post("/api/studies/std_demo_ro/research", headers=headers)
    assert demo_research.status_code == 403

    # A study the caller cannot read at all must stay a 404 (no existence leak).
    hidden = client.post(
        "/api/study/generate-personas",
        json={"study_id": "std_hidden_ro", "study_prompt": "probe", "roles": []},
        headers=headers,
    )
    assert hidden.status_code == 404


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


def test_authenticated_user_cannot_mutate_another_tenants_resources(client):
    """A signed-in caller is not a free pass: every child resource (run,
    dataset, persona, audience) must be re-checked against the study — and the
    tenant — being authorised, not just resolved by id."""
    import asyncio

    from bebshax.behavioral.orm import BehavioralTestRuns, BehavioralTests
    from bebshax.db.models import DatasetSources, SavedAudiences, Studies

    headers = _seed_two_tenants("xten")
    _seed([
        BehavioralTests(
            id="bt_vic_xten",
            study_id="std_vic_xten",
            user_id="usr_vic_xten",
            name="Victim Test",
            test_type="pricing_test",
        ),
        BehavioralTestRuns(
            id="btr_vic_xten",
            behavioral_test_id="bt_vic_xten",
            study_id="std_vic_xten",
            user_id="usr_vic_xten",
            status="completed",
            persona_count=1,
        ),
        DatasetSources(
            id="ds_vic_xten",
            user_id="usr_vic_xten",
            study_id="std_vic_xten",
            name="Victim Dataset",
            status="ready",
            source_type="url",
            source_url="https://example.invalid/victim.csv",
        ),
        SavedAudiences(id="aud_vic_xten", user_id="usr_vic_xten", name="Victim Audience"),
    ])

    probes = [
        # Direct study mutation.
        ("PATCH", "/api/studies/std_vic_xten", {"json": {"title": "Defaced"}}),
        ("DELETE", "/api/studies/std_vic_xten", {}),
        # Child resources reached through a study the attacker DOES own.
        ("POST", "/api/studies/std_att_xten/behavioral-tests/runs/btr_vic_xten/retry-failed", {}),
        ("DELETE", "/api/studies/std_att_xten/datasets/ds_vic_xten", {}),
        ("POST", "/api/studies/std_att_xten/datasets/ds_vic_xten/refresh", {}),
        ("GET", "/api/studies/std_att_xten/datasets/ds_vic_xten", {}),
        ("POST", "/api/studies/std_att_xten/personas/per_vic_xten/regenerate", {}),
        # Child resources addressed directly.
        ("DELETE", "/api/datasets/ds_vic_xten", {}),
        ("POST", "/api/datasets/ds_vic_xten/refresh", {}),
        ("DELETE", "/api/audiences/aud_vic_xten", {}),
        # Tenant id smuggled through the body.
        (
            "POST",
            "/api/datasets/url",
            {"json": {"url": "https://example.invalid/x.csv", "name": "p", "study_id": "std_vic_xten"}},
        ),
        (
            "POST",
            "/api/copilot/study/generate-personas",
            {"json": {"study_id": "std_vic_xten", "study_prompt": "probe", "roles": []}},
        ),
        ("POST", "/api/audiences", {"json": {"name": "probe", "study_id": "std_vic_xten"}}),
    ]

    failures = []
    for method, url, kwargs in probes:
        resp = client.request(method, url, headers=headers, **kwargs)
        if resp.status_code not in _REFUSAL_CODES:
            failures.append(f"{method} {url} -> {resp.status_code}")
    assert not failures, "cross-tenant access as an authenticated user: " + "; ".join(failures)

    async def victim_rows_intact():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            study = await session.get(Studies, "std_vic_xten")
            assert study is not None and study.title == "Victim Study"
            assert await session.get(DatasetSources, "ds_vic_xten") is not None
            assert await session.get(SavedAudiences, "aud_vic_xten") is not None
            run = await session.get(BehavioralTestRuns, "btr_vic_xten")
            assert run is not None and run.status == "completed"

    asyncio.run(victim_rows_intact())


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
