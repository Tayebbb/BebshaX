"""Two behavioral-test bugs the business-matrix run exposed once the 409 was gone.

1. ``POST .../behavioral-tests/{id}/runs`` read only ``test.description`` for the
   scenario, while ``create`` stores the scenario in ``behavioral_test_scenarios``.
   A test created with ``scenario_text`` alone (the documented API) could never be
   run: 400 ``scenario_required``. The frontend papered over it by sending a
   made-up "Evaluation for <name>" prompt — the simulation then ran on text no
   researcher wrote.
2. ``StudyReportService`` rendered ``len(t.scenarios)`` for every behavioral test,
   but ``BehavioralTests`` declares no ``scenarios`` relationship -> AttributeError
   -> HTTP 500 for any study that had a behavioral test at all.
"""

import json
import uuid

from sqlalchemy import select
from starlette.testclient import TestClient

from bebshax.behavioral.orm import BehavioralTestRuns, BehavioralTests, BehavioralTestScenarios
from bebshax.db.models import Personas
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter

_FIXTURE_USER = "usr_test_fixture"  # seeded by the auth_headers fixture
_SCENARIO = "The kettle is priced at £89 with a £14 replacement element. Would you buy it?"


def _install_router(app, reply: str) -> FakeAdapter:
    adapter = FakeAdapter(
        routes=[FakeRoute(candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"), reply=reply)]
    )
    router = PoolRouter(
        {name: adapter for name in ("openrouter", "freellmpool", "ollama", "pollinations")},
        on_provenance=app.state.provenance_sink,
    )
    app.state.llm_service = router
    app.state.llm_router = router
    return adapter


def _create_study(client: TestClient, headers) -> str:
    res = client.post(
        "/api/studies",
        json={"type": "interviews", "prompt": "A repairable electric kettle sold direct-to-consumer in the UK"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


async def _add_persona(app, study_id: str) -> str:
    pid = f"per_{uuid.uuid4().hex[:12]}"
    async with app.state.db_sessionmaker() as session:
        session.add(
            Personas(
                id=pid,
                study_id=study_id,
                user_id=_FIXTURE_USER,
                owner_id=_FIXTURE_USER,
                name="Priya Shah",
                archetype="Repair-minded renter",
                bio="Bristol renter who keeps appliances for a decade.",
                country_code="GB",
            )
        )
        await session.commit()
    return pid


def _create_test(client: TestClient, headers, study_id: str, **fields) -> dict:
    res = client.post(
        f"/api/studies/{study_id}/behavioral-tests",
        json={"name": "Launch price", "test_type": "pricing_test", **fields},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Bug 1: a run uses the test's stored scenario
# ---------------------------------------------------------------------------

async def test_run_uses_the_scenario_stored_at_creation(api_test_app: TestClient, auth_headers):
    study_id = _create_study(api_test_app, auth_headers)
    persona_id = await _add_persona(api_test_app.app, study_id)
    # The documented shape: scenario_text, no description.
    test = _create_test(api_test_app, auth_headers, study_id, scenario_title="Launch price", scenario_text=_SCENARIO)
    assert test.get("description") in (None, "")
    _install_router(
        api_test_app.app,
        json.dumps({"decision": "buy", "probability": 0.7, "confidence": "medium", "reasoning_summary": "Ten-year guarantee beats replacing a £25 kettle every two years.", "key_factors": ["durability"], "motivators": ["repairability"], "objections": ["upfront price"]}),
    )

    res = api_test_app.post(
        f"/api/studies/{study_id}/behavioral-tests/{test['id']}/runs",
        json={"target_population_type": "selected_personas", "target_persona_ids": [persona_id]},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    run = res.json()
    assert run["scenario_snapshot"]["scenario_text"] == _SCENARIO
    assert run["scenario_snapshot"]["title"] == "Launch price"

    async with api_test_app.app.state.db_sessionmaker() as session:
        scenario = (
            await session.execute(select(BehavioralTestScenarios).where(BehavioralTestScenarios.behavioral_test_id == test["id"]))
        ).scalar_one()
        stored_run = await session.get(BehavioralTestRuns, run["id"])
    # The run is linked to the stored scenario it was resolved from.
    assert stored_run.scenario_id == scenario.id


async def test_run_prefers_the_callers_scenario_text_over_the_stored_one(api_test_app: TestClient, auth_headers):
    study_id = _create_study(api_test_app, auth_headers)
    persona_id = await _add_persona(api_test_app.app, study_id)
    test = _create_test(api_test_app, auth_headers, study_id, scenario_text=_SCENARIO)
    _install_router(api_test_app.app, json.dumps({"decision": "hesitate", "probability": 0.4, "reasoning_summary": "At £120 the maths no longer works for me."}))

    res = api_test_app.post(
        f"/api/studies/{study_id}/behavioral-tests/{test['id']}/runs",
        json={"scenario_text": "Now priced at £120.", "target_population_type": "selected_personas", "target_persona_ids": [persona_id]},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["scenario_snapshot"]["scenario_text"] == "Now priced at £120."


async def test_run_naming_a_foreign_scenario_id_is_refused_not_substituted(api_test_app: TestClient, auth_headers):
    """A caller who names scenario X must not get the description run under X's id."""
    study_id = _create_study(api_test_app, auth_headers)
    await _add_persona(api_test_app.app, study_id)
    test = _create_test(api_test_app, auth_headers, study_id, description="Fallback description", scenario_text=_SCENARIO)

    res = api_test_app.post(
        f"/api/studies/{study_id}/behavioral-tests/{test['id']}/runs",
        json={"scenario_id": "bts_not_this_tests", "target_population_type": "all"},
        headers=auth_headers,
    )
    assert res.status_code == 404, res.text
    assert res.json()["error_code"] == "scenario_not_found"
    async with api_test_app.app.state.db_sessionmaker() as session:
        runs = (await session.execute(select(BehavioralTestRuns).where(BehavioralTestRuns.behavioral_test_id == test["id"]))).scalars().all()
    assert runs == []


async def test_run_with_no_scenario_anywhere_is_refused_not_invented(api_test_app: TestClient, auth_headers):
    study_id = _create_study(api_test_app, auth_headers)
    await _add_persona(api_test_app.app, study_id)
    # Bypass create()'s validation to build the legacy shape: a test row with
    # neither description nor scenario row.
    test_id = f"bt_{uuid.uuid4().hex[:16]}"
    async with api_test_app.app.state.db_sessionmaker() as session:
        session.add(BehavioralTests(id=test_id, study_id=study_id, user_id=_FIXTURE_USER, name="Bare test", test_type="pricing_test", status="ready"))
        await session.commit()

    res = api_test_app.post(
        f"/api/studies/{study_id}/behavioral-tests/{test_id}/runs", json={"target_population_type": "all"}, headers=auth_headers
    )
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == "scenario_required"


# ---------------------------------------------------------------------------
# Bug 2: a report can be generated for a study that has a behavioral test
# ---------------------------------------------------------------------------

async def test_report_generation_survives_a_behavioral_test(api_test_app: TestClient, auth_headers):
    study_id = _create_study(api_test_app, auth_headers)
    await _add_persona(api_test_app.app, study_id)
    _create_test(api_test_app, auth_headers, study_id, scenario_text=_SCENARIO)
    adapter = _install_router(
        api_test_app.app,
        json.dumps(
            {
                "executive_summary": "One synthetic persona; one pricing test defined but not yet run.",
                "key_findings": ["Priya Shah (persona) values a ten-year guarantee."],
                "limitations": "No interviews, no evidence claims.",
            }
        ),
    )

    res = api_test_app.post(f"/api/studies/{study_id}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 201, res.text
    assert res.json()["metrics"]["synthesis_source"] == "llm"
    # The model was told about the test — with a real run count, not a crash.
    prompt = adapter.requests[-1].messages[-1].content
    assert '"behavioral_simulations"' in prompt
    assert '"run_count": 0' in prompt
    assert "Launch price" in prompt
