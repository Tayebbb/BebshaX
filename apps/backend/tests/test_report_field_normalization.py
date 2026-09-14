"""Report fields are fitted to the StudyReports column shapes before the row is built.

Observed live on Postgres: the model returned ``target_market_summary`` as
``{"demographics": {...}, "psychographics": {...}}`` for a Text column ->
asyncpg ``DataError: expected str, got dict`` -> HTTP 500. SQLite accepts any
Python value for TEXT, so the unit suite never saw it. The normaliser keeps
every word the model wrote (rendered readably) and invents nothing.
"""

import json

from sqlalchemy import select
from starlette.testclient import TestClient

from bebshax.db.models import Personas, StudyReports
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.research.report_service import _LIST_FIELDS, _TEXT_FIELDS, _TITLE_MAX, _normalize_report_fields

_FIXTURE_USER = "usr_test_fixture"  # seeded by the auth_headers fixture

# The exact shape observed live (ollama/llama3.2:3b).
_LIVE_TARGET_MARKET = {
    "demographics": {"age_range": "25-40", "location": "Berlin", "income": "3,200-5,000 EUR/month"},
    "psychographics": {"values": ["convenience", "trust"], "lifestyle": "time-poor professionals"},
}


def test_dict_text_section_is_rendered_to_readable_text_with_all_content_kept():
    fields = _normalize_report_fields({"target_market_summary": _LIVE_TARGET_MARKET})
    text = fields["target_market_summary"]
    assert isinstance(text, str)
    for word in ("demographics", "age_range: 25-40", "location: Berlin", "3,200-5,000 EUR/month", "psychographics", "convenience", "trust", "time-poor professionals"):
        assert word in text
    # Nested keys are indented under their parent, one level per depth.
    assert "demographics:\n  age_range: 25-40" in text
    assert "  values:\n    - convenience\n    - trust" in text


def test_string_list_field_is_wrapped_and_list_text_field_becomes_bullets():
    fields = _normalize_report_fields(
        {
            "recommendations": "Pilot with 20 Berlin dog owners before pricing above 18 EUR.",
            "validation_summary": ["Demand signal is moderate.", "Pricing tolerance unknown."],
            "major_risks": {"risk": "Walkers churn in winter", "severity": "high"},
        }
    )
    assert fields["recommendations"] == ["Pilot with 20 Berlin dog owners before pricing above 18 EUR."]
    assert fields["validation_summary"] == "- Demand signal is moderate.\n- Pricing tolerance unknown."
    assert fields["major_risks"] == [{"risk": "Walkers churn in winter", "severity": "high"}]


def test_none_and_junk_shapes_become_honest_absences():
    fields = _normalize_report_fields({"key_findings": None, "opportunities": 42, "strongest_segments": "   ", "limitations": None, "metrics": "n/a", "title": {"x": 1}})
    assert fields["key_findings"] == [] and fields["opportunities"] == [] and fields["strongest_segments"] == []
    assert fields["limitations"] is None
    assert fields["metrics"] == {}
    assert fields["title"] is None  # the model gave no usable title -> caller falls back
    # Missing sections default per column type.
    for name in _TEXT_FIELDS:
        if name != "limitations":
            assert fields[name] is None
    for name in _LIST_FIELDS:
        if name not in ("key_findings", "opportunities", "strongest_segments"):
            assert fields[name] == []


def test_strings_and_lists_of_the_right_shape_pass_through_untouched():
    data = {
        "executive_summary": "Berlin professionals want reliable walkers.",
        "key_findings": ["Fees decide the order."],
        "evidence_findings": [{"title": "t", "claim": "c", "confidence": 0.5, "source": "s"}],
        "metrics": {"demand_score": 61},
        "title": "Dog-walking report",
        "extra_key": "kept",
    }
    fields = _normalize_report_fields(data)
    for key, value in data.items():
        assert fields[key] == value


def test_long_title_is_bounded_at_a_word_boundary_and_logged(caplog):
    title = " ".join(f"word{i}" for i in range(60))
    with caplog.at_level("INFO", logger="bebshax.research.report_service"):
        fields = _normalize_report_fields({"title": title})
    assert len(fields["title"]) <= _TITLE_MAX == 256
    assert title.startswith(fields["title"]) and fields["title"].split()[-1].startswith("word")
    assert not fields["title"].endswith(" ")
    assert any("report title cut" in rec.message for rec in caplog.records)


def test_numbers_bools_and_nulls_render_as_json_scalars():
    text = _normalize_report_fields({"market_context_summary": {"share": 35.5, "growing": True, "unknown": None, "empty": []}})["market_context_summary"]
    assert text == "share: 35.5\ngrowing: true\nunknown: null\nempty: []"


# --- API level: the live failure, end to end ---------------------------------


def _install_router(app, reply: str) -> FakeAdapter:
    adapter = FakeAdapter(routes=[FakeRoute(candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"), reply=reply)])
    router = PoolRouter({n: adapter for n in ("openrouter", "freellmpool", "ollama", "pollinations")}, on_provenance=app.state.provenance_sink)
    app.state.llm_service = router
    app.state.llm_router = router
    return adapter


async def _study_with_persona(client: TestClient, headers) -> str:
    res = client.post("/api/studies", json={"type": "interviews", "prompt": "A dog-walking app for busy professionals in Berlin"}, headers=headers)
    assert res.status_code == 201, res.text
    study_id = res.json()["id"]
    async with client.app.state.db_sessionmaker() as session:
        session.add(Personas(id=f"per_{study_id[-8:]}", study_id=study_id, user_id=_FIXTURE_USER, owner_id=_FIXTURE_USER, name="Lena Vogel", archetype="Time-poor dog owner"))
        # A report needs at least one finding; personas alone are refused.
        session.add(Conversations(id=f"conv_{study_id[-8:]}", study_id=study_id, user_id=_FIXTURE_USER, persona_id=f"per_{study_id[-8:]}", objective="demand_validation", status="completed", turn_count=1))
        session.add(ConversationTurns(id=f"turn_{study_id[-8:]}", conversation_id=f"conv_{study_id[-8:]}", turn_number=1, role="persona", content="I book everything from my phone between meetings."))
        await session.commit()
    return study_id


async def test_report_generation_survives_structured_text_sections(api_test_app: TestClient, auth_headers):
    study_id = await _study_with_persona(api_test_app, auth_headers)
    _install_router(
        api_test_app.app,
        json.dumps(
            {
                "title": "Berlin dog-walking validation",
                "executive_summary": {"headline": "Moderate demand", "detail": "One persona only; no interviews yet."},
                "key_findings": ["Lena Vogel books services from her phone."],
                "target_market_summary": _LIVE_TARGET_MARKET,
                "recommendations": "Interview five dog owners before pricing.",
                "validation_summary": ["Signal: moderate", "Evidence: thin"],
                "metrics": {"demand_score": 55},
            }
        ),
    )

    res = api_test_app.post(f"/api/studies/{study_id}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert isinstance(body["target_market_summary"], str)
    for word in ("age_range: 25-40", "Berlin", "convenience", "time-poor professionals"):
        assert word in body["target_market_summary"]
    assert body["executive_summary"] == "headline: Moderate demand\ndetail: One persona only; no interviews yet."
    assert body["recommendations"] == ["Interview five dog owners before pricing."]
    assert body["validation_summary"] == "- Signal: moderate\n- Evidence: thin"
    assert body["title"] == "Berlin dog-walking validation"
    # Computed counts and the model's own metric coexist.
    assert body["metrics"]["total_personas"] == 1 and body["metrics"]["demand_score"] == 55
    assert body["metrics"]["synthesis_source"] == "llm"

    async with api_test_app.app.state.db_sessionmaker() as session:
        row = (await session.execute(select(StudyReports).where(StudyReports.study_id == study_id))).scalar_one()
        assert isinstance(row.target_market_summary, str) and isinstance(row.executive_summary, str)
        assert isinstance(row.recommendations, list)
