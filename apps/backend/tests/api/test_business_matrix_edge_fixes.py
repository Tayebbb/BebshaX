"""Edge cases found by the business-matrix audit (2026-09-08), each reproduced
live against Postgres through the HTTP API before being fixed:

* script/generate fabricated a script from a title-only study;
* reports/generate (sync and job) wrote a report for a study with zero data;
* ai-review scored an empty study 95/100 because a report row counted as material;
* generate-personas silently clamped role counts (0 -> 1, 11 -> 3);
* study titles echoed raw HTML from the prompt.

Every fix is an explicit, coded refusal (R2) — never a substituted value.
"""

import asyncio
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from bebshax.auth.models import Users
from bebshax.db.models import Base, Personas, Studies, StudyReports
from bebshax.evaluation.ai_judge import JUDGE_NOTHING_TO_REVIEW, judge_study
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.research.report_service import REPORT_REQUIRES_DATA
from bebshax.utils.explicit_failures import InsufficientInput
from bebshax.utils.title_generator import generate_deterministic_study_title

_FIXTURE_USER = "usr_test_fixture"  # seeded by the auth_headers fixture


def _fake_adapter(app) -> FakeAdapter:
    return app.state.llm_adapters["openrouter"]


def _install_router(app, reply: str) -> FakeAdapter:
    """Replace the shared router with one whose model answers ``reply``."""
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


def _create_study(client: TestClient, headers, **fields) -> dict:
    res = client.post("/api/studies", json={"type": "interviews", **fields}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def _add_persona(app, study_id: str) -> None:
    async with app.state.db_sessionmaker() as session:
        session.add(
            Personas(
                id=f"per_{study_id[-8:]}",
                study_id=study_id,
                user_id=_FIXTURE_USER,
                owner_id=_FIXTURE_USER,
                name="Lena Vogel",
                archetype="Time-poor dog owner",
                bio="Consultant in Berlin Mitte with a Border Collie.",
            )
        )
        await session.commit()


async def _add_interview_turn(app, study_id: str) -> str:
    """One completed interview with a single persona answer: the smallest real finding."""
    interview_id = f"conv_{study_id[-8:]}"
    async with app.state.db_sessionmaker() as session:
        session.add(
            Conversations(
                id=interview_id, study_id=study_id, user_id=_FIXTURE_USER, persona_id=f"per_{study_id[-8:]}",
                objective="demand_validation", status="completed", turn_count=2, question_count=1,
            )
        )
        session.add(ConversationTurns(id=f"turn_{study_id[-8:]}_1", conversation_id=interview_id, turn_number=1, role="interviewer", content="How do you arrange walks today?"))
        session.add(ConversationTurns(id=f"turn_{study_id[-8:]}_2", conversation_id=interview_id, turn_number=2, role="persona", content="I text a neighbour the night before; it falls through about once a week."))
        await session.commit()
    return interview_id


async def _add_report_row(app, study_id: str) -> None:
    async with app.state.db_sessionmaker() as session:
        session.add(
            StudyReports(
                id=f"rep_{study_id[-8:]}",
                study_id=study_id,
                user_id=_FIXTURE_USER,
                version=1,
                title="Stale report",
                executive_summary="No data available.",
            )
        )
        await session.commit()


async def _poll_job(client: TestClient, url: str, headers) -> dict:
    for _ in range(200):
        res = client.get(url, headers=headers)
        assert res.status_code == 200, res.text
        job = res.json()
        if job["status"] != "running":
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("job never terminated")


# ---------------------------------------------------------------------------
# Bug 2: script/generate must not fall back to the study title
# ---------------------------------------------------------------------------

async def test_script_generation_refuses_title_only_study(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, title="Just a title")
    assert study["prompt"] in (None, "")
    calls_before = len(_fake_adapter(api_test_app.app).requests)

    res = api_test_app.post(
        f"/api/studies/{study['id']}/script/generate", json={"question_count": 3}, headers=auth_headers
    )
    assert res.status_code == 400, res.text
    body = res.json()
    assert body["error_code"] == "business_description_required"
    assert "Describe the business idea" in body["detail"]
    # No model was asked to invent a business from a title.
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before

    # A whitespace-only payload prompt does not rescue it either.
    res_ws = api_test_app.post(
        f"/api/studies/{study['id']}/script/generate", json={"prompt": "   "}, headers=auth_headers
    )
    assert res_ws.status_code == 400 and res_ws.json()["error_code"] == "business_description_required"


async def test_script_generation_still_uses_the_stored_study_prompt(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")
    adapter = _install_router(
        api_test_app.app,
        json.dumps({"questions": ["How do you arrange walks today?", "What went wrong last time?", "What would 18 EUR buy?"]}),
    )

    res = api_test_app.post(f"/api/studies/{study['id']}/script/generate", json={}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "llm" and len(res.json()["questions"]) == 3
    assert "dog-walking app" in adapter.requests[-1].messages[-1].content


# ---------------------------------------------------------------------------
# Bug 3: a report needs data — sync route and background job
# ---------------------------------------------------------------------------

async def test_report_generation_refuses_a_study_with_no_data(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")
    calls_before = len(_fake_adapter(api_test_app.app).requests)

    res = api_test_app.post(f"/api/studies/{study['id']}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == REPORT_REQUIRES_DATA
    assert "run interviews or research" in res.json()["detail"]

    # Nothing was spent and nothing was written: no row, study not "completed".
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before
    assert api_test_app.get(f"/api/studies/{study['id']}/reports", headers=auth_headers).json() == []
    refreshed = api_test_app.get(f"/api/studies/{study['id']}", headers=auth_headers).json()
    assert refreshed["status"] != "completed" and refreshed["step"] == 1


async def test_report_job_surfaces_missing_data_as_a_failed_job(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")

    res = api_test_app.post(f"/api/studies/{study['id']}/reports/generate/jobs", json={}, headers=auth_headers)
    assert res.status_code == 202, res.text
    job = await _poll_job(
        api_test_app, f"/api/studies/{study['id']}/reports/generate/jobs/{res.json()['job_id']}", auth_headers
    )
    assert job["status"] == "failed"
    assert job["error_code"] == REPORT_REQUIRES_DATA
    assert "run interviews or research" in job["error"]
    assert job["result"] is None and job["finished_at"] is not None


async def test_report_generation_refuses_personas_without_any_findings(api_test_app: TestClient, auth_headers):
    """Live 2026-09-14: five personas, no interviews, no evidence produced a report
    asserting a confirmed survey and a 78 % demand signal. The panel is not data."""
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")
    await _add_persona(api_test_app.app, study["id"])
    calls_before = len(_fake_adapter(api_test_app.app).requests)

    res = api_test_app.post(f"/api/studies/{study['id']}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == REPORT_REQUIRES_DATA
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before
    assert api_test_app.get(f"/api/studies/{study['id']}/reports", headers=auth_headers).json() == []


async def test_report_generation_proceeds_with_one_interview_turn_and_strips_ungrounded_sections(
    api_test_app: TestClient, auth_headers,
):
    """One answered interview question admits a report; sections the captured
    inputs cannot support (evidence, datasets, behavioral results, invented turn
    citations) are removed and recorded, and scores stay measured or null."""
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")
    await _add_persona(api_test_app.app, study["id"])
    interview_id = await _add_interview_turn(api_test_app.app, study["id"])
    _install_router(
        api_test_app.app,
        json.dumps(
            {
                "executive_summary": "One synthetic interview; the persona relies on an informal neighbour arrangement.",
                "key_findings": ["Lena Vogel (persona) reports her current arrangement fails weekly."],
                "evidence_findings": [{"title": "Survey of 100 owners", "claim": "75% want an app", "status": "Confirmed"}],
                "dataset_findings": [{"name": "owners.csv", "insight": "invented"}],
                "behavioral_results": [{"test_type": "A/B", "scenario": "invented", "average_likelihood": 0.75}],
                "interview_findings": [
                    {"topic": "reliability", "finding": "Informal cover fails weekly.", "turn_citations": [f"{interview_id} per_x turn 2"], "is_synthetic": True},
                    {"topic": "price", "finding": "Would pay 18 EUR.", "turn_citations": ["conv_doesnotexist turn 4"], "is_synthetic": False},
                ],
                "limitations": "Single synthetic interview; no evidence or datasets.",
                "metrics": {"demand_score": 0.78, "confidence_score": 0.85},
            }
        ),
    )

    res = api_test_app.post(f"/api/studies/{study['id']}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["metrics"]["synthesis_source"] == "llm" and body["metrics"]["total_interviews"] == 1
    assert body["evidence_findings"] == [] and body["dataset_findings"] == [] and body["behavioral_results"] == []
    assert [item["topic"] for item in body["interview_findings"]] == ["reliability"]
    grounding = body["metrics"]["grounding"]
    assert set(grounding["removed_sections"]) == {"evidence_findings", "dataset_findings", "behavioral_results", "interview_findings"}
    assert "turns" in grounding["sources_present"] and "evidence_claims" not in grounding["sources_present"]
    # Interview turns are a measurable input, so the model's scores are kept as labelled synthetic signals.
    assert body["metrics"]["demand_score"] == 0.78 and grounding["scores_nulled"] == []


# ---------------------------------------------------------------------------
# Bug 4: a report row alone is not reviewable material for the AI judge
# ---------------------------------------------------------------------------

async def test_ai_review_refuses_a_study_whose_only_artefact_is_a_report(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, prompt="A dog-walking app for busy professionals in Berlin")
    await _add_report_row(api_test_app.app, study["id"])
    calls_before = len(_fake_adapter(api_test_app.app).requests)

    res = api_test_app.post(f"/api/studies/{study['id']}/ai-review", headers=auth_headers)
    assert res.status_code == 400, res.text
    assert res.json()["error_code"] == JUDGE_NOTHING_TO_REVIEW
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before  # judge never asked


async def test_judge_study_needs_a_primary_artefact_not_just_a_report():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    class _NeverCalled:
        calls = 0

        async def complete(self, request):
            _NeverCalled.calls += 1
            raise AssertionError("the judge must not be asked to score an empty study")

    async with maker() as session:
        session.add(Users(id="usr_rep", email="rep@example.com", full_name="R", hashed_password="pw"))
        session.add(Studies(id="std_rep", user_id="usr_rep", title="Empty", prompt="Nothing here yet", status="draft"))
        session.add(
            StudyReports(
                id="rep_only", study_id="std_rep", user_id="usr_rep", version=1,
                title="Stale", executive_summary="No data available.",
            )
        )
        await session.commit()
        study = await session.get(Studies, "std_rep")
        with pytest.raises(InsufficientInput) as info:
            await judge_study(session, study, _NeverCalled())
    assert info.value.error_code == JUDGE_NOTHING_TO_REVIEW
    assert "report alone" in info.value.detail
    assert _NeverCalled.calls == 0
    await engine.dispose()


# ---------------------------------------------------------------------------
# Bug 5: role counts are validated, never clamped
# ---------------------------------------------------------------------------

def _role(count: int, *, selected: bool = True, role_id: str = "r1", title: str = "Dog owner") -> dict:
    return {"id": role_id, "role": title, "description": "Owns a dog in Berlin", "count": count, "selected": selected}


@pytest.mark.parametrize("count", [0, 4, 11])
async def test_generate_personas_rejects_out_of_range_role_counts(api_test_app: TestClient, auth_headers, count):
    calls_before = len(_fake_adapter(api_test_app.app).requests)

    res = api_test_app.post(
        "/api/study/generate-personas",
        json={"study_prompt": "A dog-walking app for busy professionals in Berlin", "roles": [_role(count)]},
        headers=auth_headers,
    )
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["error_code"] == "validation_error"
    assert body["max_personas_per_role"] == 3
    # The message names the offending role and the limit.
    assert "Dog owner" in body["detail"] and str(count) in body["detail"] and "3" in body["detail"]
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before  # refused before any LLM spend


async def test_generate_personas_accepts_the_maximum_count(ml_api_app: TestClient, ml_auth_headers):
    adapter = _fake_adapter(ml_api_app.app)
    calls_before = len(adapter.requests)

    res = ml_api_app.post(
        "/api/study/generate-personas",
        json={"study_prompt": "Food delivery and meal planning", "roles": [_role(3)]},
        headers=ml_auth_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["personas"]) == 3 and body["failed_roles"] == []
    assert len(adapter.requests) == calls_before
    assert {persona["role_id"] for persona in body["personas"]} == {"r1"}
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in body["personas"]}) == 3


async def test_generate_personas_ignores_unselected_zero_count_roles(ml_api_app: TestClient, ml_auth_headers):
    adapter = _fake_adapter(ml_api_app.app)
    calls_before = len(adapter.requests)

    res = ml_api_app.post(
        "/api/study/generate-personas",
        json={
            "study_prompt": "Food delivery and meal planning",
            "roles": [
                _role(0, selected=False, role_id="r0", title="Professional walker"),
                _role(2, role_id="r1", title="Dog owner"),
            ],
        },
        headers=ml_auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["failed_roles"] == []
    assert len(adapter.requests) == calls_before
    personas = res.json()["personas"]
    assert len(personas) == 2
    assert {persona["role_id"] for persona in personas} == {"r1"}
    assert {persona["role_title"] for persona in personas} == {"Dog owner"}
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in personas}) == 2


def test_model_proposed_role_counts_are_normalised_to_the_limit():
    from bebshax.api.copilot import MAX_PERSONAS_PER_ROLE, _roles_from

    roles = _roles_from({"roles": [{"id": "role_1", "role": "DOG OWNER", "count": 11, "selected": True}]})
    assert MAX_PERSONAS_PER_ROLE == 3
    assert [r.count for r in roles] == [3]


async def test_all_unselected_roles_is_a_plain_selection_error(api_test_app: TestClient, auth_headers):
    """The old fallback took "the first three" unselected roles; with count
    validation that produced a 422 about a role the caller never selected."""
    calls_before = len(_fake_adapter(api_test_app.app).requests)
    res = api_test_app.post(
        "/api/study/generate-personas",
        json={
            "study_prompt": "A dog-walking app for busy professionals in Berlin",
            "roles": [_role(0, selected=False, role_id="r0"), _role(0, selected=False, role_id="r1", title="Walker")],
        },
        headers=auth_headers,
    )
    assert res.status_code == 400, res.text
    assert "Select at least one persona role" in res.json()["detail"]
    assert len(_fake_adapter(api_test_app.app).requests) == calls_before


async def test_duplicate_role_ids_are_refused(api_test_app: TestClient, auth_headers):
    """Studies saved before ids became server-owned carry one id on every
    role; sibling exclusion and name de-duplication are keyed by id."""
    res = api_test_app.post(
        "/api/study/generate-personas",
        json={
            "study_prompt": "A dog-walking app for busy professionals in Berlin",
            "roles": [_role(1, role_id="role_{short_id}"), _role(1, role_id="role_{short_id}", title="Walker")],
        },
        headers=auth_headers,
    )
    assert res.status_code == 422, res.text
    assert res.json()["error_code"] == "validation_error"
    assert "role_{short_id}" in res.json()["detail"]


def test_attribute_with_a_placeholder_detail_keeps_its_real_title():
    """A real goal whose description came back as "..." is a goal with no
    description, not a dropped goal (it feeds Personas.goals)."""
    from bebshax.api.copilot import _clean_persona_payload

    p = _clean_persona_payload(
        {
            "name": "Lena Vogel",
            "attributes": [
                {"category": "Goals", "title": "Reliable evening walks", "description": "..."},
                {"category": "Needs", "title": "Core Need", "description": "What they need from this product to adopt it"},
            ],
            "badges": [
                {"label": "MONTHLY BUDGET", "value": "Realistic amount for this product"},
                {"label": "COMMUTE", "value": "45 min by S-Bahn"},
            ],
        }
    )
    assert [a["title"] for a in p["attributes"]] == ["Reliable evening walks"]
    assert p["attributes"][0]["description"] is None
    assert [b["label"] for b in p["badges"]] == ["COMMUTE"]


def test_role_ids_are_server_owned_and_unique():
    """Observed live: the model echoed the prompt's example id ``role_{short_id}``
    on every role; the frontend keys selection and count changes by id, so
    duplicates would make one click hit several roles."""
    from bebshax.api.copilot import _roles_from

    roles = _roles_from({"roles": [
        {"id": "role_{short_id}", "role": "DAILY COMMUTER", "count": 3, "selected": True},
        {"id": "role_{short_id}", "role": "FLEET MANAGER", "count": 3, "selected": True},
        {"id": "role_{short_id}", "role": "CITY PLANNER", "count": 0, "selected": False},
    ]})
    ids = [r.id for r in roles]
    assert len(set(ids)) == 3
    assert not any("{" in i for i in ids)
    assert [r.role for r in roles] == ["DAILY COMMUTER", "FLEET MANAGER", "CITY PLANNER"]


# ---------------------------------------------------------------------------
# Bug 6: study titles never echo HTML
# ---------------------------------------------------------------------------

def test_deterministic_title_strips_html_markup():
    title = generate_deterministic_study_title("<script>alert(1)</script> A dog-walking app in Berlin")
    assert "<" not in title and ">" not in title
    assert "Dog-Walking App in Berlin" in title

    assert "<" not in generate_deterministic_study_title('<img src=x onerror="alert(1)">Coffee cart at Berlin stations')
    # Markup-only input falls back to the canonical title rather than an empty string.
    assert generate_deterministic_study_title("<b></b>", study_type="interviews") == "Customer Discovery & Workflow Study"
    # Angle brackets in prose are not tags and survive.
    assert generate_deterministic_study_title("Tutoring for kids < 10 and adults > 60") == "Tutoring for Kids < 10 and Adults > 60"


async def test_created_study_title_contains_no_html(api_test_app: TestClient, auth_headers):
    study = _create_study(api_test_app, auth_headers, prompt="<script>alert(1)</script> A dog-walking app in Berlin")
    assert "<" not in study["title"] and ">" not in study["title"]
    assert "Dog-Walking App in Berlin" in study["title"]
    async with api_test_app.app.state.db_sessionmaker() as session:
        stored = (await session.execute(select(Studies).where(Studies.id == study["id"]))).scalar_one()
    assert "<script" not in stored.title
