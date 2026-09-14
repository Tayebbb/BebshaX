"""API hardening: one error envelope + request ids for every response.

Pins the contract the frontend relies on: every error body is
``{"detail", "error_code", "request_id", ...}`` and every response carries
``X-Request-ID`` (echoed when the client's value is well-formed, generated
otherwise). LLM-layer failures render the rich envelope (attempts, failure
kinds, llm_request_id) instead of a flattened 503/413 string.
"""

import json
import re

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from bebshax.api.errors import (
    MAX_REQUEST_BODY_BYTES,
    APIError,
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    register_exception_handlers,
)
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Personas, Studies
from bebshax.interview.engine import InterviewEngine
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import FailureKind
from bebshax.llm.router import PoolRouter

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_OWNER = "usr_env_owner"


def _owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': _OWNER})}"}


async def _seed_interview_fixture(app) -> tuple[str, str]:
    """Owner + study + persona rows; returns (study_id, persona_id)."""
    async with app.state.db_sessionmaker() as session:
        if await session.get(Users, _OWNER) is None:
            session.add(
                Users(
                    id=_OWNER, email="env-owner@example.com", full_name="Env Owner",
                    hashed_password="x", is_active=True, is_verified=True,
                )
            )
        session.add(Studies(id="std_env", user_id=_OWNER, title="Envelope Study", status="in_progress"))
        session.add(
            Personas(
                id="per_env", study_id="std_env", user_id=_OWNER, owner_id=_OWNER,
                name="Envelope Persona", version=1, demographics={"age": "27"},
            )
        )
        await session.commit()
    return "std_env", "per_env"


def _dead_router(**candidate_kwargs) -> PoolRouter:
    """Every attempt fails with SERVER_ERROR: the router exhausts all candidates."""
    dead = FakeAdapter(
        [
            FakeRoute(
                candidate=RouteCandidate(provider="pollinations", model="dead-model", **candidate_kwargs),
                behaviors=[FailureKind.SERVER_ERROR] * 8,
            )
        ]
    )
    return PoolRouter({"openrouter": dead, "freellmpool": dead, "ollama": dead})


def _tiny_window_router() -> PoolRouter:
    """The only route cannot hold even the identity card: pre-flight raises CWE."""
    tiny = FakeAdapter(
        [FakeRoute(candidate=RouteCandidate(provider="pollinations", model="tiny", context_window=32))]
    )
    return PoolRouter({"openrouter": tiny, "freellmpool": tiny, "ollama": tiny})


# ---------------------------------------------------------------------------
# X-Request-ID
# ---------------------------------------------------------------------------

async def test_every_response_carries_a_generated_request_id(api_test_app: TestClient):
    resp = api_test_app.get("/api/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid and _HEX32.match(rid), "generated ids are uuid4 hex"


async def test_well_formed_client_request_id_is_echoed(api_test_app: TestClient):
    resp = api_test_app.get("/api/health", headers={"X-Request-ID": "judge-run_42"})
    assert resp.headers["X-Request-ID"] == "judge-run_42"


@pytest.mark.parametrize("bad", ["a" * 65, "has space", "semi;colon", "<script>"])
async def test_malformed_client_request_id_is_replaced(api_test_app: TestClient, bad: str):
    resp = api_test_app.get("/api/health", headers={"X-Request-ID": bad})
    rid = resp.headers["X-Request-ID"]
    assert rid != bad and _HEX32.match(rid)


async def test_error_body_request_id_matches_header(api_test_app: TestClient):
    resp = api_test_app.get("/api/studies/std_does_not_exist", headers={"X-Request-ID": "trace-1"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["request_id"] == "trace-1" == resp.headers["X-Request-ID"]


# ---------------------------------------------------------------------------
# Envelope shapes
# ---------------------------------------------------------------------------

async def test_404_envelope_has_error_code_and_request_id(api_test_app: TestClient):
    resp = api_test_app.get("/api/studies/std_missing")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error_code"] == "not_found"
    assert isinstance(body["detail"], str) and body["detail"]
    assert _HEX32.match(body["request_id"])


async def test_422_envelope_keeps_pydantic_detail_and_adds_message(api_test_app: TestClient):
    # `message` must be a string (title too long) — the frontend showed
    # "[object Object]" when it rendered the raw pydantic list.
    await _seed_interview_fixture(api_test_app.app)
    resp = api_test_app.post(
        "/api/studies", json={"title": "x" * 257, "prompt": "ok"}, headers=_owner_headers()
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "validation_error"
    assert isinstance(body["detail"], list) and body["detail"][0]["loc"][-1] == "title"
    assert isinstance(body["message"], str) and "title" in body["message"]
    assert "request_id" in body


async def test_duplicate_client_supplied_id_is_409_not_500(api_test_app: TestClient):
    """IntegrityError → 409 conflict. Audiences are the write path that still
    honours a client id (study ids are always server-generated, see below)."""
    await _seed_interview_fixture(api_test_app.app)
    payload = {"id": "aud_dup_1", "name": "Dup", "persona_ids": []}
    first = api_test_app.post("/api/audiences", json=payload, headers=_owner_headers())
    assert first.status_code == 201
    second = api_test_app.post("/api/audiences", json=payload, headers=_owner_headers())
    assert second.status_code == 409
    body = second.json()
    assert body["error_code"] == "conflict"
    assert "request_id" in body
    assert "IntegrityError" not in json.dumps(body) and "UNIQUE" not in json.dumps(body)


async def test_client_supplied_study_id_is_ignored_on_create(api_test_app: TestClient):
    """The frontend never sends an id on create; a caller-picked primary key
    let one visitor collide with (or probe for) another's study."""
    await _seed_interview_fixture(api_test_app.app)
    first = api_test_app.post(
        "/api/studies", json={"id": "study_mine", "prompt": "A"}, headers=_owner_headers()
    )
    second = api_test_app.post(
        "/api/studies", json={"id": "study_mine", "prompt": "B"}, headers=_owner_headers()
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != "study_mine"
    assert first.json()["id"] != second.json()["id"]


# ---------------------------------------------------------------------------
# LLM-layer failures → rich envelopes
# ---------------------------------------------------------------------------

async def test_all_candidates_failed_is_503_with_attempts(api_test_app: TestClient):
    app = api_test_app.app
    study_id, persona_id = await _seed_interview_fixture(app)
    started = api_test_app.post(
        f"/api/studies/{study_id}/personas/{persona_id}/interviews",
        json={"objective": "demand_validation"},
        headers=_owner_headers(),
    )
    assert started.status_code == 201, started.text
    interview_id = started.json()["id"]

    saved_engine = app.state.interview_engine
    app.state.interview_engine = InterviewEngine(
        _dead_router(), app.state.db_sessionmaker, memory=app.state.memory_service
    )
    try:
        resp = api_test_app.post(
            f"/api/studies/{study_id}/interviews/{interview_id}/messages",
            json={"content": "What would you pay?"},
            headers=_owner_headers(),
        )
    finally:
        app.state.interview_engine = saved_engine

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["error_code"] == "all_candidates_failed"
    assert body["detail"] == "No AI route could serve this request — all candidates failed."
    assert body["llm_request_id"] and _HEX32.match(body["request_id"])
    assert body["attempts"], "the envelope must show what was tried"
    for attempt in body["attempts"]:
        assert set(attempt) == {"provider", "model", "failure_kind", "fallback_reason"}
        assert attempt["failure_kind"] == "SERVER_ERROR"
    assert isinstance(body["routing_path"], list)
    # Provider error bodies stay in provenance/logs, never in the response.
    assert "scripted failure" not in resp.text


async def test_context_window_exceeded_is_413_with_estimate(api_test_app: TestClient):
    app = api_test_app.app
    study_id, persona_id = await _seed_interview_fixture(app)
    started = api_test_app.post(
        f"/api/studies/{study_id}/personas/{persona_id}/interviews",
        json={"objective": "demand_validation"},
        headers=_owner_headers(),
    )
    interview_id = started.json()["id"]

    saved_engine = app.state.interview_engine
    app.state.interview_engine = InterviewEngine(
        _tiny_window_router(), app.state.db_sessionmaker, memory=app.state.memory_service
    )
    try:
        resp = api_test_app.post(
            f"/api/studies/{study_id}/interviews/{interview_id}/messages",
            json={"content": "Tell me about your week."},
            headers=_owner_headers(),
        )
    finally:
        app.state.interview_engine = saved_engine

    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert body["error_code"] == "context_window_exceeded"
    assert body["estimated_tokens"] > 32
    assert body["largest_window"] == 32
    assert "Nothing was truncated" in body["detail"]


async def test_sse_error_event_carries_error_code_and_llm_request_id(api_test_app: TestClient):
    app = api_test_app.app
    study_id, persona_id = await _seed_interview_fixture(app)
    started = api_test_app.post(
        f"/api/studies/{study_id}/personas/{persona_id}/interviews",
        json={"objective": "demand_validation"},
        headers=_owner_headers(),
    )
    interview_id = started.json()["id"]

    saved_engine = app.state.interview_engine
    app.state.interview_engine = InterviewEngine(
        _dead_router(), app.state.db_sessionmaker, memory=app.state.memory_service
    )
    try:
        resp = api_test_app.post(
            f"/api/studies/{study_id}/interviews/{interview_id}/messages/stream",
            json={"content": "Hi"},
            headers={**_owner_headers(), "X-Request-ID": "sse-trace"},
        )
    finally:
        app.state.interview_engine = saved_engine

    assert resp.status_code == 200
    assert "event: error" in resp.text
    data_line = next(line for line in resp.text.splitlines() if line.startswith("data: "))
    event = json.loads(data_line[len("data: "):])
    assert event["kind"] == "no_route"  # legacy field kept for existing clients
    assert event["error_code"] == "all_candidates_failed"
    assert event["llm_request_id"] and event["request_id"] == "sse-trace"
    assert event["attempts"][0]["failure_kind"] == "SERVER_ERROR"


# ---------------------------------------------------------------------------
# Body cap, rate-limit envelope, unhandled exceptions
# ---------------------------------------------------------------------------

async def test_body_over_two_mib_is_413_payload_too_large(api_test_app: TestClient):
    blob = {"prompt": "x" * (3 * 1024 * 1024)}
    resp = api_test_app.post("/api/studies", json=blob, headers=_owner_headers())
    assert resp.status_code == 413
    body = resp.json()
    assert body["error_code"] == "payload_too_large"
    assert body["max_bytes"] == MAX_REQUEST_BODY_BYTES
    assert resp.headers["X-Request-ID"] == body["request_id"]


async def test_dataset_upload_route_is_exempt_from_the_global_body_cap(api_test_app: TestClient):
    """Uploads enforce their own 25 MB ceiling; a 3 MB CSV must reach the route
    (it is rejected there for a different reason, never as payload_too_large)."""
    await _seed_interview_fixture(api_test_app.app)  # the upload route needs a real user
    csv = b"a,b\n" + b"1,2\n" * (3 * 1024 * 1024 // 4)
    resp = api_test_app.post(
        "/api/datasets/upload",
        files={"file": ("big.csv", csv, "text/csv")},
        data={"name": "Big"},
        headers=_owner_headers(),
    )
    # Reached the route: the parser's own row cap answers with its specific code,
    # never the global `payload_too_large` envelope.
    assert resp.status_code == 413, resp.text
    assert resp.json()["error_code"] == "dataset_limits_exceeded"


async def test_rate_limited_envelope_has_request_id_and_error_code(api_test_app: TestClient):
    """The 429 handler speaks to the user (not slowapi's "5 per 1 minute"), carries
    Retry-After, and keeps the standard envelope keys."""
    from bebshax.api.limiter import limiter

    limiter._limiter.storage.reset()
    try:
        last = None
        for _ in range(6):
            last = api_test_app.post(
                "/api/auth/signin", json={"email": "nobody@example.com", "password": "wrong-pass1"}
            )
        assert last is not None and last.status_code == 429, last.text
        body = last.json()
        assert body["error_code"] == "rate_limited"
        assert body["detail"].startswith("Too many requests from your connection. Try again in ")
        assert body["message"] == body["detail"]
        assert body["limit"] == "5 per 1 minute"
        assert 1 <= body["retry_after_seconds"] <= 60
        assert last.headers["Retry-After"] == str(body["retry_after_seconds"])
        assert body["request_id"] == last.headers["X-Request-ID"]
    finally:
        limiter._limiter.storage.reset()


def _bare_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret-db-password-in-message")

    @app.get("/typed")
    async def typed():
        raise APIError(409, "Already running.", error_code="run_in_progress", extra={"run_id": "r1"})

    @app.post("/stale")
    async def stale():
        from sqlalchemy.orm.exc import StaleDataError

        raise StaleDataError("UPDATE statement on table 'studies' expected to update 1 row(s); 0 were matched.")

    return app


def test_lost_revision_race_is_a_409_write_conflict_not_a_500(caplog):
    """Persona generation once answered 500 when a queued study PATCH bumped the
    revision counter mid-save; the caller must get a retryable conflict."""
    client = TestClient(_bare_app(), raise_server_exceptions=False)
    with caplog.at_level("WARNING"):
        resp = client.post("/stale", headers={"X-Request-ID": "race-1"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "write_conflict"
    assert body["request_id"] == "race-1"
    assert "Reload and try again" in body["detail"]
    assert "studies" not in resp.text
    assert any("race-1" in rec.getMessage() for rec in caplog.records)


def test_unhandled_exception_is_generic_500_with_request_id(caplog):
    client = TestClient(_bare_app(), raise_server_exceptions=False)
    with caplog.at_level("ERROR"):
        resp = client.get("/boom", headers={"X-Request-ID": "crash-1"})
    assert resp.status_code == 500
    body = resp.json()
    assert body == {"detail": "Internal server error", "error_code": "internal_error", "request_id": "crash-1"}
    assert resp.headers["X-Request-ID"] == "crash-1"
    # The message goes to the log with the request id — never to the client.
    assert "secret-db-password-in-message" not in resp.text
    assert any("crash-1" in rec.getMessage() for rec in caplog.records)


def test_api_error_extra_fields_land_at_top_level():
    resp = TestClient(_bare_app()).get("/typed")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error_code"] == "run_in_progress" and body["run_id"] == "r1"
    assert body["detail"] == "Already running."


def test_unhandled_500_keeps_cors_headers_for_cross_origin_spa(caplog):
    """Starlette's ServerErrorMiddleware sits outside CORS, so a bare 500 is an
    opaque network error for a cross-origin SPA. The inner envelope middleware
    must answer first so the browser can read error_code + request_id."""
    from starlette.middleware.cors import CORSMiddleware

    from bebshax.api.errors import UnhandledExceptionEnvelopeMiddleware

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://spa.example"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret-db-password-in-message")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level("ERROR"):
        resp = client.get(
            "/boom", headers={"Origin": "https://spa.example", "X-Request-ID": "crash-cors"}
        )
    assert resp.status_code == 500
    assert resp.headers["access-control-allow-origin"] == "https://spa.example"
    assert resp.headers["X-Request-ID"] == "crash-cors"
    assert resp.json() == {
        "detail": "Internal server error",
        "error_code": "internal_error",
        "request_id": "crash-cors",
    }
    assert "secret-db-password-in-message" not in resp.text
    assert any("crash-cors" in rec.getMessage() for rec in caplog.records)


def test_access_log_emits_one_line_per_request_without_query_string(caplog):
    client = TestClient(_bare_app())
    with caplog.at_level("INFO", logger="bebshax.access"):
        client.get("/typed?token=SECRET", headers={"X-Request-ID": "log-1"})
    lines = [r for r in caplog.records if r.name == "bebshax.access"]
    assert len(lines) == 1
    msg = lines[0].getMessage()
    assert "method=GET" in msg and "path=/typed" in msg and "status=409" in msg
    assert "request_id=log-1" in msg and "duration_ms=" in msg
    assert "SECRET" not in msg
