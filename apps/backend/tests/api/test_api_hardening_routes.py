"""API hardening: route reachability, health probes, provenance redaction."""

import asyncio
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import LLMRequests, Personas, Studies
from bebshax.llm.types import TaskType
from bebshax.main import create_app

_OWNER = "usr_routes_owner"


def _owner_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': _OWNER})}"}


async def _seed_owner_and_study(app, study_id: str) -> None:
    async with app.state.db_sessionmaker() as session:
        if await session.get(Users, _OWNER) is None:
            session.add(
                Users(
                    id=_OWNER, email="routes-owner@example.com", full_name="Routes Owner",
                    hashed_password="x", is_active=True, is_verified=True,
                )
            )
        session.add(Studies(id=study_id, user_id=_OWNER, title="Routes", status="in_progress"))
        await session.commit()


# ---------------------------------------------------------------------------
# Route shadowing
# ---------------------------------------------------------------------------

def _iter_effective_routes(router, prefix: str = "") -> Iterator[tuple[str, frozenset[str]]]:
    """Yield (full_path, methods) in MATCHING order, descending into included
    routers exactly as FastAPI does (0.141 keeps them as nested routers)."""
    for item in router.routes:
        inner = getattr(item, "original_router", None)
        if inner is not None:
            yield from _iter_effective_routes(inner, prefix + item.include_context.prefix)
            continue
        methods = getattr(item, "methods", None)
        path = getattr(item, "path", None)
        if methods and path is not None:
            yield prefix + path, frozenset(methods)


def _shadows(earlier: str, later: str) -> bool:
    """True when every request matching `later` is captured by `earlier` first:
    same segment count, and each earlier segment is either identical or a
    `{param}` where `later` has a literal."""
    a, b = earlier.split("/"), later.split("/")
    if len(a) != len(b):
        return False
    if not any(x.startswith("{") and not y.startswith("{") for x, y in zip(a, b)):
        return False
    return all(x == y or x.startswith("{") for x, y in zip(a, b))


def test_no_literal_route_is_shadowed_by_an_earlier_param_route():
    routes = list(_iter_effective_routes(create_app().router))
    assert len(routes) > 50, "route walk must see the real API, not an empty shell"
    shadowed = [
        (sorted(methods), path, earlier_path)
        for i, (path, methods) in enumerate(routes)
        for earlier_path, earlier_methods in routes[:i]
        if methods & earlier_methods and _shadows(earlier_path, path)
    ]
    assert shadowed == [], f"unreachable routes (declared after a matching {{param}} sibling): {shadowed}"


async def test_behavioral_compare_is_reachable_and_validates_run_ids(api_test_app: TestClient):
    """Used to 404 as "Behavioral test 'compare' not found" — the literal route was
    declared after `/behavioral-tests/{test_id}`."""
    await _seed_owner_and_study(api_test_app.app, "std_cmp")
    missing = api_test_app.get("/api/studies/std_cmp/behavioral-tests/compare", headers=_owner_headers())
    assert missing.status_code == 400, missing.text
    assert missing.json()["error_code"] == "bad_request"
    assert "compare" not in missing.json()["detail"]

    ok = api_test_app.get(
        "/api/studies/std_cmp/behavioral-tests/compare",
        params={"run_ids": "btr_nope_1, btr_nope_2"},
        headers=_owner_headers(),
    )
    assert ok.status_code == 200
    assert ok.json() == {"study_id": "std_cmp", "compared_run_count": 0, "runs": []}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def test_health_reports_db_local_tier_and_sink_counters(api_test_app: TestClient):
    body = api_test_app.get("/api/health").json()
    assert body["status"] == "ok"  # legacy shape intact
    assert body["db"] == "ok"
    assert isinstance(body["local_tier_up"], bool)
    assert set(body["sink"]) == {"written", "dropped", "db_errors"}


async def test_ready_is_200_when_db_answers(api_test_app: TestClient):
    resp = api_test_app.get("/api/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "db": "ok"}


class _BrokenSession:
    async def __aenter__(self):
        raise ConnectionRefusedError("db down")

    async def __aexit__(self, *exc):
        return False


def test_ready_is_503_and_health_degrades_when_db_is_unreachable():
    app = create_app()
    app.state.db_sessionmaker = lambda: _BrokenSession()  # every session open fails
    client = TestClient(app)

    ready = client.get("/api/health/ready")
    assert ready.status_code == 503
    body = ready.json()
    assert body["error_code"] == "database_unavailable"
    assert body["db"] == "unreachable"
    assert "request_id" in body

    health = client.get("/api/health")
    assert health.status_code == 200, "liveness stays up so the operator can read the snapshot"
    assert health.json()["db"] == "unreachable"
    assert health.json()["local_tier_up"] is None  # lifespan did not run on this bare app


def test_db_probe_gives_up_after_its_timeout():
    from bebshax.api.health import probe_database

    class _HangingSession:
        async def __aenter__(self):
            await asyncio.sleep(10)

        async def __aexit__(self, *exc):
            return False

    class _App:
        class state:
            db_sessionmaker = staticmethod(lambda: _HangingSession())

    assert asyncio.run(probe_database(_App, timeout_s=0.05)) == "unreachable"


# ---------------------------------------------------------------------------
# Provenance redaction
# ---------------------------------------------------------------------------

_DETAIL = "HTTP 500 from provider: <html>request echo: my secret prompt</html>"


async def _seed_provenance(app) -> None:
    async with app.state.db_sessionmaker() as session:
        if await session.get(Users, _OWNER) is None:
            session.add(
                Users(
                    id=_OWNER, email="routes-owner@example.com", full_name="Routes Owner",
                    hashed_password="x", is_active=True, is_verified=True,
                )
            )
        session.add(
            Personas(id="per_prov_owned", owner_id=_OWNER, user_id=_OWNER, name="Owned", version=1)
        )
        session.add_all(
            [
                LLMRequests(
                    request_id="req_infra_fail",
                    task=TaskType.PERSONA_INTERVIEW,
                    pool="conversation",
                    persona_id=None,
                    success=False,
                    attempts=[{
                        "attempt_number": 1, "provider": "p", "model": "m", "success": False,
                        "failure_kind": "SERVER_ERROR", "failure_detail": _DETAIL,
                        "fallback_reason": "advancing after SERVER_ERROR",
                    }],
                ),
                LLMRequests(
                    request_id="req_owned_fail",
                    task=TaskType.PERSONA_INTERVIEW,
                    pool="conversation",
                    persona_id="per_prov_owned",
                    success=False,
                    attempts=[{
                        "attempt_number": 1, "provider": "p", "model": "m", "success": False,
                        "failure_kind": "RATE_LIMITED", "failure_detail": _DETAIL,
                        "fallback_reason": None,
                    }],
                ),
            ]
        )
        await session.commit()


async def test_anonymous_provenance_shows_failure_kind_but_not_failure_detail(api_test_app: TestClient):
    await _seed_provenance(api_test_app.app)
    resp = api_test_app.get("/api/provenance")
    assert resp.status_code == 200
    items = {i["request_id"]: i for i in resp.json()["items"]}
    infra = items["req_infra_fail"]
    assert infra["attempts"][0]["failure_kind"] == "SERVER_ERROR"
    assert infra["attempts"][0]["failure_detail"] is None
    assert "my secret prompt" not in resp.text
    # Owned rows are not even listed to anonymous callers.
    assert "req_owned_fail" not in items


async def test_owner_sees_failure_detail_on_their_own_rows_only(api_test_app: TestClient):
    await _seed_provenance(api_test_app.app)
    resp = api_test_app.get("/api/provenance", headers=_owner_headers())
    items = {i["request_id"]: i for i in resp.json()["items"]}
    assert items["req_owned_fail"]["attempts"][0]["failure_detail"] == _DETAIL
    assert items["req_infra_fail"]["attempts"][0]["failure_detail"] is None


def test_redact_attempts_is_pure_and_keeps_other_fields():
    from bebshax.api.routes import redact_attempts

    src = [{"provider": "p", "failure_kind": "TIMEOUT", "failure_detail": "x"}, {"provider": "q"}]
    out = redact_attempts(src)
    assert out == [{"provider": "p", "failure_kind": "TIMEOUT", "failure_detail": None}, {"provider": "q"}]
    assert src[0]["failure_detail"] == "x", "input must not be mutated (ORM JSON column)"


@pytest.mark.parametrize("path", ["/api/health", "/api/health/ready", "/api/provenance"])
async def test_probe_and_provenance_routes_carry_request_ids(api_test_app: TestClient, path: str):
    assert api_test_app.get(path).headers.get("X-Request-ID")
