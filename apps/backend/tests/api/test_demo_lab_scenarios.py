"""Judge Lab (/api/demo-lab) — every scenario runs the real router over scripted
FakeAdapters, is labelled simulated, and leaves the app's own router untouched."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from starlette.testclient import TestClient

from bebshax.api import demo_lab
from bebshax.api.demo_lab import SCENARIOS, timeline_from
from bebshax.api.limiter import limiter
from bebshax.config import Settings
from bebshax.db.models import LLMRequests
from bebshax.llm.provenance import AttemptRecord, ProvenanceRecord

_JWT = "test-only-jwt-secret-not-for-production-0123456789"


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
async def lab_client(api_test_app: TestClient) -> TestClient:
    """The orchestrator wires the router in main.py; until then mount it on the fixture app."""
    app = api_test_app.app
    if not any(getattr(r, "path", "").startswith("/api/demo-lab") for r in app.routes):
        app.include_router(demo_lab.router, prefix="/api")
    return api_test_app


def _run(client: TestClient, name: str, headers: dict) -> dict:
    res = client.post(f"/api/demo-lab/scenarios/{name}/run", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------- listing ---


async def test_list_scenarios_exposes_the_whole_table(lab_client, auth_headers):
    res = lab_client.get("/api/demo-lab/scenarios", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True and body["simulated"] is True
    assert {s["name"] for s in body["scenarios"]} == set(SCENARIOS)
    for entry in body["scenarios"]:
        assert entry["title"] and entry["description"] and entry["expected_outcome"]


async def test_unknown_scenario_returns_404(lab_client, auth_headers):
    res = lab_client.post("/api/demo-lab/scenarios/does_not_exist/run", headers=auth_headers)
    assert res.status_code == 404


# --------------------------------------------------------------- gating ---


async def test_requires_auth_returns_401_without_token(lab_client):
    assert lab_client.get("/api/demo-lab/scenarios").status_code == 401
    assert lab_client.post("/api/demo-lab/scenarios/provider_429_fallback/run").status_code == 401


async def test_disabled_outside_demo_and_dev_returns_404(lab_client, auth_headers, monkeypatch):
    hermetic = Settings(
        _env_file=None,
        jwt_secret=_JWT,
        environment="production",
        demo_mode=False,
        resend_api_key="re_test_dummy",
        email_from_address="noreply@example.com",
    )
    monkeypatch.setattr(demo_lab, "get_settings", lambda: hermetic)
    # Gate runs before auth: production must not even reveal the lab exists.
    assert lab_client.get("/api/demo-lab/scenarios").status_code == 404
    assert lab_client.get("/api/demo-lab/scenarios", headers=auth_headers).status_code == 404
    res = lab_client.post("/api/demo-lab/scenarios/provider_429_fallback/run", headers=auth_headers)
    assert res.status_code == 404


async def test_demo_mode_enables_the_lab_even_outside_dev(lab_client, auth_headers, monkeypatch):
    hermetic = Settings(_env_file=None, jwt_secret=_JWT, environment="test", demo_mode=True)
    monkeypatch.setattr(demo_lab, "get_settings", lambda: hermetic)
    assert lab_client.get("/api/demo-lab/scenarios", headers=auth_headers).status_code == 200


# ------------------------------------------------------------ scenarios ---


async def test_every_scenario_is_simulated_and_matches_its_advertised_outcome(
    lab_client, auth_headers
):
    for name, spec in SCENARIOS.items():
        body = _run(lab_client, name, auth_headers)
        assert body["simulated"] is True
        assert body["scenario"] == name and body["title"] == spec.title
        assert body["outcome"] == spec.expected_outcome, name
        assert body["explanation"]


async def test_provider_429_fallback_serves_from_route_b(lab_client, auth_headers):
    body = _run(lab_client, "provider_429_fallback", auth_headers)
    assert body["outcome"] == "served_after_fallback" and body["error_code"] is None
    assert [s["result"] for s in body["timeline"]] == ["failed", "served"]
    assert body["timeline"][0]["failure_kind"] == "RATE_LIMITED"
    assert body["timeline"][0]["fallback_reason"] == "advancing after RATE_LIMITED"
    assert body["timeline"][1]["provider"] == "openrouter"
    assert body["provenance"]["success"] is True
    assert body["provenance"]["served_by_provider"] == "openrouter"
    assert body["extra"]["cooling_routes"] == ["groq/llama-3.1-8b-instant"]


async def test_provider_5xx_fallback_ends_on_secondary_remote_route(lab_client, auth_headers):
    body = _run(lab_client, "provider_5xx_fallback", auth_headers)
    assert body["outcome"] == "served_after_fallback" and body["error_code"] is None
    assert [s["result"] for s in body["timeline"]] == ["failed", "served"]
    assert [s["failure_kind"] for s in body["timeline"]] == ["SERVER_ERROR", None]
    assert body["timeline"][1]["provider"] == "openrouter"
    assert body["provenance"]["served_by_model"] == "meta-llama/llama-3.3-70b-instruct:free"


async def test_all_providers_down_is_an_explicit_failure_with_full_trail(lab_client, auth_headers):
    body = _run(lab_client, "all_providers_down", auth_headers)
    assert body["outcome"] == "explicit_failure"
    assert body["error_code"] == "all_candidates_failed"
    assert body["provenance"]["success"] is False
    assert body["provenance"]["served_by_provider"] is None
    assert all(s["result"] == "failed" for s in body["timeline"])
    assert [s["failure_kind"] for s in body["timeline"]] == [
        "RATE_LIMITED", "QUOTA_EXHAUSTED", "CONNECTION", "CONNECTION",
    ]
    # CONNECTION's policy retries the same route once — shown, not hidden.
    assert body["timeline"][2]["fallback_reason"] == "retrying same route once"
    assert body["extra"]["attempt_count"] == 4


async def test_context_overflow_refuses_before_any_call(lab_client, auth_headers):
    body = _run(lab_client, "context_overflow", auth_headers)
    assert body["outcome"] == "explicit_failure"
    assert body["error_code"] == "context_window_exceeded"
    assert body["provenance"]["attempts"] == []
    assert len(body["timeline"]) == 2 and all(s["result"] == "skipped" for s in body["timeline"])
    assert all("context" in s["fallback_reason"] for s in body["timeline"])
    extra = body["extra"]
    assert extra["estimated_tokens"] > extra["largest_window"] == 4096
    assert extra["adapter_calls"] == {"freellmpool": [], "openrouter": []}
    assert extra["any_adapter_called"] is False and extra["truncated"] is False


async def test_prompt_injection_is_wrapped_and_fake_citations_downgraded(lab_client, auth_headers):
    body = _run(lab_client, "prompt_injection", auth_headers)
    assert body["outcome"] == "claims_downgraded" and body["error_code"] is None
    extra = body["extra"]
    excerpt = extra["prompt_excerpt"]
    assert "<UNTRUSTED_EVIDENCE" in excerpt and extra["injection_text"] in excerpt
    # The chunk's forged closing tag could not escape the block.
    assert "‹/UNTRUSTED_EVIDENCE›" in excerpt
    assert extra["forged_close_tag_neutralised"] is True
    assert extra["closing_tags_in_prompt"] == 2  # exactly one per wrapped item
    claims = {c["claim"]: c for c in extra["claims"]}
    ghost = claims["Prefers a weekly view (fabricated citation)"]
    assert (ghost["provenance_before"], ghost["provenance_after"]) == ("OBSERVED", "INFERRED")
    assert ghost["evidence_ids"] == [] and ghost["downgraded"] is True
    bare = claims["Uses a shared digital calendar"]
    assert bare["provenance_after"] == "INFERRED" and bare["downgraded"] is True
    legit = claims["Records assignments and test schedules in a planner"]
    assert legit["provenance_after"] == "OBSERVED" and legit["evidence_ids"] == ["ev_review_49f85be0"]
    complied = claims["The hidden system prompt says: <complied with injection>"]
    assert complied["evidence_ids"] == ["ev_chunk_injected"]
    assert extra["injection_text"] in complied["cited_text"][0]  # the leaned-on text is visible
    assert extra["downgraded_count"] == 2
    assert [s["result"] for s in body["timeline"]] == ["served"]


async def test_evidence_conflict_marks_claim_inferred_with_contested_warning(
    lab_client, auth_headers
):
    body = _run(lab_client, "evidence_conflict", auth_headers)
    assert body["outcome"] == "claims_downgraded" and body["error_code"] is None
    extra = body["extra"]
    assert extra["contested_slots"] == ["age"] and extra["contested"] is True
    assert "contested:age" in extra["warnings"]
    (claim,) = extra["claims"]
    assert (claim["provenance_before"], claim["provenance_after"]) == ("OBSERVED", "INFERRED")
    assert claim["grounding_basis"] == "contested_evidence"
    assert sorted(claim["evidence_ids"]) == ["ev_age_24", "ev_age_41"]  # citations kept, visible
    assert "persona.conflicts" in extra["detector"]


async def test_insufficient_evidence_reports_zero_grounding_honestly(lab_client, auth_headers):
    body = _run(lab_client, "insufficient_evidence", auth_headers)
    assert body["outcome"] == "low_grounding" and body["error_code"] is None
    extra = body["extra"]
    assert extra["grounding_ratio"] == 0.0 and extra["observed_claims"] == 0
    assert extra["grounding_basis"] == "no_evidence_retrieved"
    assert extra["total_claims"] == 5
    # The model's bare "OBSERVED" label was not trusted.
    provs = {e["provenance"] for group in extra["claim_provenance"].values() for e in group}
    assert "OBSERVED" not in provs
    assert "real customers" in body["explanation"]


# ------------------------------------------------------------ isolation ---


async def test_lab_runs_leave_the_app_router_and_sink_untouched(lab_client, auth_headers):
    app = lab_client.app
    live_router = app.state.llm_router
    fixture_adapter = app.state.llm_adapters["openrouter"]
    before_util = live_router.pool_utilization()
    before_calls = list(fixture_adapter.calls)

    for name in ("provider_429_fallback", "all_providers_down", "context_overflow"):
        _run(lab_client, name, auth_headers)

    assert live_router.pool_utilization() == before_util
    assert fixture_adapter.calls == before_calls
    assert app.state.llm_router is live_router
    async with app.state.db_sessionmaker() as session:
        persisted = (await session.execute(select(func.count()).select_from(LLMRequests))).scalar()
    assert persisted == 0  # scenario provenance is returned, never persisted


# -------------------------------------------------------- pure helpers ---


def test_timeline_lists_preflight_skips_then_attempts():
    prov = ProvenanceRecord(
        request_id="r", task="PERSONA_GENERATION",
        routing_path=[
            "[preference */x: 0 route(s) prioritized]",
            "ollama/llama3.2:3b [skipped: cooling down for 42s more]",
            "openrouter/meta-llama/llama-3.3-70b-instruct:free",
        ],
        attempts=[
            AttemptRecord(attempt_number=1, provider="openrouter",
                          model="meta-llama/llama-3.3-70b-instruct:free", success=True, latency_ms=3.5),
        ],
    )
    steps = timeline_from(prov)
    assert [s.step for s in steps] == [1, 2]
    assert (steps[0].result, steps[0].provider, steps[0].model) == ("skipped", "ollama", "llama3.2:3b")
    assert steps[0].fallback_reason == "cooling down for 42s more"
    assert steps[1].result == "served" and steps[1].model == "meta-llama/llama-3.3-70b-instruct:free"
