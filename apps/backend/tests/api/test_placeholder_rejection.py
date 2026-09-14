"""The prompts' own example strings never reach the user (bebshax.llm.placeholders).

Observed live: POST /api/study/copilot returned the literal example reply from
its SYSTEM_PROMPT JSON template. Every site that shows the model a JSON example
now rejects an echoed placeholder through its existing retry-then-
UnusableModelOutput path — nothing is ever substituted.
"""

import json

import pytest
from starlette.testclient import TestClient

from bebshax.db.models import Personas
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter

_FIXTURE_USER = "usr_test_fixture"  # seeded by the auth_headers fixture
_ROUTE = "pollinations/deepseek-r1"


def _install_router(app, replies: list[str], *, default: str = "{}") -> FakeAdapter:
    """Router whose single route answers ``replies`` in order, then ``default``."""
    adapter = FakeAdapter(
        routes=[FakeRoute(candidate=RouteCandidate(provider="pollinations", model="deepseek-r1"), replies=list(replies), reply=default)]
    )
    router = PoolRouter({n: adapter for n in ("openrouter", "freellmpool", "ollama", "pollinations")}, on_provenance=app.state.provenance_sink)
    app.state.llm_router = router
    app.state.llm_service = router
    return adapter


def _copilot_reply(reply: str, **extra) -> str:
    return json.dumps({"reply": reply, "suggested_study_type": "interviews", "is_ready_for_approval": False, "research_goal_card": None, "suggested_roles": [], **extra})


_PLACEHOLDER_REPLY = _copilot_reply("Conversational explanation and question to display to the user")
_REAL_REPLY = _copilot_reply("A dog-walking marketplace for Berlin professionals — are you validating demand or willingness to pay first?")
_MESSAGES = [{"role": "user", "content": "An on-demand dog-walking app for busy professionals in Berlin"}]


# --- copilot reply -----------------------------------------------------------


def test_copilot_placeholder_reply_is_retried_and_the_real_reply_is_returned(api_test_app: TestClient, auth_headers):
    adapter = _install_router(api_test_app.app, [_PLACEHOLDER_REPLY, _REAL_REPLY])

    res = api_test_app.post("/api/study/copilot", json={"messages": _MESSAGES}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reply"].startswith("A dog-walking marketplace for Berlin professionals")
    assert body["fallback_reason"] == "retried_after_unparseable_reply"
    assert body["served_by"] == _ROUTE
    assert len(adapter.requests) == 2


def test_copilot_refuses_when_every_reply_is_the_prompt_example(api_test_app: TestClient, auth_headers):
    adapter = _install_router(api_test_app.app, [_PLACEHOLDER_REPLY, _PLACEHOLDER_REPLY])

    res = api_test_app.post("/api/study/copilot", json={"messages": _MESSAGES}, headers=auth_headers)
    assert res.status_code == 502, res.text
    body = res.json()
    assert body["error_code"] == "copilot_reply_unparseable" and body["attempts"] == 2
    assert "Conversational explanation" not in res.text  # never shown, never substituted
    assert len(adapter.requests) == 2


def test_goal_card_still_holding_template_slots_is_not_approvable(api_test_app: TestClient, auth_headers):
    card = {
        "title": "RESEARCH GOAL",
        "summary": "You want to research whether Berlin professionals will pay 18 EUR per walk. Does this capture what you're looking for?",
        "target_audience": "Professionals in Berlin who own a dog and work 50+ hours a week",
        "core_hypothesis": "[Core assumption to validate]",
    }
    roles = [{"id": "role_1", "role": "TIME-POOR DOG OWNER", "description": "Pays for convenience", "count": 3, "selected": True}]
    _install_router(api_test_app.app, [_copilot_reply("Here is the proposal.", is_ready_for_approval=True, research_goal_card=card, suggested_roles=roles)])

    res = api_test_app.post("/api/study/copilot", json={"messages": _MESSAGES * 3}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_ready_for_approval"] is False and body["research_goal_card"] is None
    assert [r["role"] for r in body["suggested_roles"]] == ["TIME-POOR DOG OWNER"]  # real roles survive


def test_placeholder_roles_are_dropped_from_the_copilot_card(api_test_app: TestClient, auth_headers):
    card = {"title": "RESEARCH GOAL", "summary": "Validate 18 EUR walks in Berlin. Does this capture what you're looking for?", "target_audience": "Berlin dog owners", "core_hypothesis": "Owners pay for reliability"}
    roles = [
        {"id": "role_1", "role": "ROLE TITLE IN CAPS", "description": "Specific reason this persona type is crucial for validating the exact hypotheses in their business context", "count": 3, "selected": True},
        {"id": "role_2", "role": "ANOTHER ROLE", "description": "Why this role is relevant", "count": 3, "selected": True},
        {"id": "role_3", "role": "FREELANCE DOG WALKER", "description": "Supply side: accepts or rejects the fee split", "count": 2, "selected": True},
    ]
    _install_router(api_test_app.app, [_copilot_reply("Proposal below.", is_ready_for_approval=True, research_goal_card=card, suggested_roles=roles)])

    res = api_test_app.post("/api/study/copilot", json={"messages": _MESSAGES * 3}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_ready_for_approval"] is True
    assert [r["role"] for r in body["suggested_roles"]] == ["FREELANCE DOG WALKER"]


# --- goal card hygiene (live 2026-09-14) -------------------------------------

_CARD = {
    "title": "RESEARCH GOAL",
    "summary": "You want to research whether Berlin professionals will pay 18 EUR per walk. Does this capture what you're looking for?",
    "target_audience": "Professionals in Berlin who own a dog",
    "core_hypothesis": "Owners pay for reliability",
}
_QUESTION = "Does this capture what you're looking for?"


def test_confirmation_question_is_kept_out_of_the_summary_and_said_once(api_test_app: TestClient, auth_headers):
    # Live: the sentence rendered twice (reply + card) and the copy stored as the
    # study prompt — research input — carried the conversational tail.
    reply = f"Here is the proposal. {_QUESTION} It is below. {_QUESTION}"
    _install_router(api_test_app.app, [_copilot_reply(reply, is_ready_for_approval=True, research_goal_card=_CARD)])

    res = api_test_app.post("/api/study/copilot", json={"messages": _MESSAGES * 3}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_ready_for_approval"] is True
    assert body["research_goal_card"]["summary"] == "You want to research whether Berlin professionals will pay 18 EUR per walk."
    assert body["reply"] == f"Here is the proposal. It is below. {_QUESTION}"
    assert body["reply"].count(_QUESTION) == 1


def test_goal_card_is_withheld_until_the_user_describes_an_idea_in_words(api_test_app: TestClient, auth_headers):
    # Live: an emoji-only conversation was answered with a full, approvable goal.
    _install_router(api_test_app.app, [_copilot_reply("Proposal below.", is_ready_for_approval=True, research_goal_card=_CARD)] * 2)

    emoji_only = [{"role": "user", "content": "🧺🧼😀👕"}, {"role": "assistant", "content": "Tell me more?"}, {"role": "user", "content": "👍 !!!"}]
    res = api_test_app.post("/api/study/copilot", json={"messages": emoji_only}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["is_ready_for_approval"] is False and res.json()["research_goal_card"] is None

    # Words in any script count; emoji in the latest turn do not undo an earlier idea.
    described = [{"role": "user", "content": "ঢাকার ছাত্রদের জন্য লন্ড্রি সার্ভিস"}, {"role": "assistant", "content": "Which campus?"}, {"role": "user", "content": "🧺🧼"}]
    res = api_test_app.post("/api/study/copilot", json={"messages": described}, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert res.json()["is_ready_for_approval"] is True


# --- suggest-roles -----------------------------------------------------------


def test_suggest_roles_filters_placeholders_and_refuses_an_all_placeholder_reply(api_test_app: TestClient, auth_headers):
    only_examples = json.dumps({"roles": [{"id": "role_x", "role": "ROLE NAME IN CAPS (max 4 words)", "description": "Specific reason this persona type is essential for validating the product hypothesis. Be concrete about what insights they provide.", "count": 3, "selected": True}]})
    mixed = json.dumps({"roles": [
        {"id": "role_1", "role": "ROLE NAME IN CAPS (max 4 words)", "description": "Why this role is relevant", "count": 3, "selected": True},
        {"id": "role_2", "role": "WEEKEND TRAVELLER", "description": "Needs multi-day care, tests price ceiling", "count": 3, "selected": True},
    ]})
    adapter = _install_router(api_test_app.app, [only_examples, mixed])
    payload = {"study_prompt": "An on-demand dog-walking app for busy professionals in Berlin"}

    res = api_test_app.post("/api/study/suggest-roles", json=payload, headers=auth_headers)
    assert res.status_code == 200, res.text
    assert [r["role"] for r in res.json()] == ["WEEKEND TRAVELLER"]
    assert len(adapter.requests) == 2  # the all-placeholder reply was retried

    _install_router(api_test_app.app, [only_examples, only_examples])
    res2 = api_test_app.post("/api/study/suggest-roles", json=payload, headers=auth_headers)
    assert res2.status_code == 502 and res2.json()["error_code"] == "roles_unparseable"


# --- generate-personas -------------------------------------------------------


def test_placeholder_llm_personas_cannot_replace_trained_profiles(ml_api_app: TestClient, ml_auth_headers, ml_training_records):
    personas = {
        "personas": [
            {"name": "Full Name", "archetype": "Descriptive Archetype", "demographics": {"occupation": "Specific Job Title"}},
            {
                "name": "Lena Vogel",
                "archetype": "Descriptive Archetype",
                "tagline": "The [Evocative Label]",
                "description": "Consultant with a Border Collie who travels twice a month.",
                "demographics": {"age": 34, "occupation": "Specific Job Title", "income_bracket": "Realistic Income", "location": "Berlin, Germany", "education": "Degree Level"},
                "badges": [
                    {"label": "MONTHLY BUDGET", "value": "Realistic amount for this product"},
                    {"label": "MONTHLY BUDGET", "value": "About 120 EUR"},
                ],
                "attributes": [
                    {"category": "Goals", "title": "Specific Goal Related to Product", "description": "What they want to achieve with this product", "provenance_class": "INFERRED", "evidence": None},
                    {"category": "Goals", "title": "Reliable evening walks on travel days", "description": "Needs a walker she can book the same afternoon.", "provenance_class": "INFERRED", "evidence": None},
                ],
            },
        ]
    }
    adapter = _install_router(ml_api_app.app, [json.dumps(personas)])
    roles = [{"id": "r1", "role": "Meal planner", "description": "Pays for convenience", "count": 2, "selected": True}]

    res = ml_api_app.post("/api/study/generate-personas", json={"study_prompt": "Meal delivery planning", "roles": roles}, headers=ml_auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert adapter.requests == []
    assert len(body["personas"]) == 2
    assert len({persona["detailed_attributes"]["ml_provenance"]["record_id"] for persona in body["personas"]}) == 2
    for persona in body["personas"]:
        source = next(record for record in ml_training_records if record.record_id == persona["detailed_attributes"]["ml_provenance"]["record_id"])
        assert persona["name"] == (source.name or f"Synthetic profile {source.record_id}")
        assert persona["demographics"]["occupation"] == source.occupation
        assert persona["demographics"]["location"] == source.location
        assert persona["description"] == source.description
        assert persona["badges"] == []
        assert persona["goals"] == source.goals
    assert "Specific Job Title" not in res.text and "Full Name" not in res.text


@pytest.mark.parametrize("ml_api_app", ["missing"], indirect=True)
def test_missing_ml_artifact_is_not_replaced_by_placeholder_llm(ml_api_app: TestClient, ml_auth_headers):
    only_example = json.dumps({"personas": [{"name": "Full Name", "demographics": {"occupation": "Specific Job Title"}}]})
    adapter = _install_router(ml_api_app.app, [only_example, only_example])
    roles = [{"id": "r1", "role": "Time-poor dog owner", "description": "Pays for convenience", "count": 1, "selected": True}]

    res = ml_api_app.post("/api/study/generate-personas", json={"study_prompt": "Meal delivery planning", "roles": roles}, headers=ml_auth_headers)
    assert res.status_code == 503, res.text
    assert res.json()["error_code"] == "ml_persona_unavailable"
    assert adapter.requests == [] and "Full Name" not in res.text


# --- script ------------------------------------------------------------------


def _study(client: TestClient, headers) -> str:
    res = client.post("/api/studies", json={"type": "interviews", "prompt": "A dog-walking app for busy professionals in Berlin"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_script_placeholder_questions_are_filtered(api_test_app: TestClient, auth_headers):
    study_id = _study(api_test_app, auth_headers)
    _install_router(api_test_app.app, [json.dumps({"questions": ["Question 1", "How do you arrange walks when you travel?", "What did the last walker get wrong?", "Question 2"]})])

    res = api_test_app.post(f"/api/studies/{study_id}/script/generate", json={"question_count": 4}, headers=auth_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["questions"] == ["How do you arrange walks when you travel?", "What did the last walker get wrong?"]
    assert body["count"] == 2 and body["fallback_reason"] is None
    stored = api_test_app.get(f"/api/studies/{study_id}", headers=auth_headers).json()
    assert stored["script_questions"] == body["questions"]


def test_script_with_fewer_than_two_real_questions_takes_the_unparseable_path(api_test_app: TestClient, auth_headers):
    study_id = _study(api_test_app, auth_headers)
    placeholders = json.dumps({"questions": ["Question 1", "Question 2", "How do you arrange walks today?"]})
    adapter = _install_router(api_test_app.app, [placeholders, placeholders])

    res = api_test_app.post(f"/api/studies/{study_id}/script/generate", json={}, headers=auth_headers)
    assert res.status_code == 502, res.text
    body = res.json()
    assert body["error_code"] == "script_unparseable" and body["attempts"] == 2
    assert len(adapter.requests) == 2
    assert api_test_app.get(f"/api/studies/{study_id}", headers=auth_headers).json()["script_questions"] in (None, [])


# --- report ------------------------------------------------------------------


async def _study_with_persona(client: TestClient, headers) -> str:
    study_id = _study(client, headers)
    async with client.app.state.db_sessionmaker() as session:
        session.add(Personas(id=f"per_{study_id[-8:]}", study_id=study_id, user_id=_FIXTURE_USER, owner_id=_FIXTURE_USER, name="Lena Vogel", archetype="Time-poor dog owner"))
        # Reports need a finding (personas alone are refused); one answered turn suffices.
        session.add(Conversations(id=f"conv_{study_id[-8:]}", study_id=study_id, user_id=_FIXTURE_USER, persona_id=f"per_{study_id[-8:]}", objective="demand_validation", status="completed", turn_count=1))
        session.add(ConversationTurns(id=f"turn_{study_id[-8:]}", conversation_id=f"conv_{study_id[-8:]}", turn_number=1, role="persona", content="I book everything from my phone between meetings."))
        await session.commit()
    return study_id


async def test_report_with_a_placeholder_executive_summary_is_refused(api_test_app: TestClient, auth_headers):
    study_id = await _study_with_persona(api_test_app, auth_headers)
    example = json.dumps({"executive_summary": "Crisp 2-3 paragraph executive summary grounded in findings", "key_findings": ["Finding 1 with concrete data"]})
    adapter = _install_router(api_test_app.app, [example, example])

    res = api_test_app.post(f"/api/studies/{study_id}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 502, res.text
    assert res.json()["error_code"] == "report_synthesis_failed"
    assert len(adapter.requests) == 2
    assert api_test_app.get(f"/api/studies/{study_id}/reports", headers=auth_headers).json() == []


async def test_report_placeholder_items_and_sections_are_dropped(api_test_app: TestClient, auth_headers):
    study_id = await _study_with_persona(api_test_app, auth_headers)
    _install_router(
        api_test_app.app,
        [
            json.dumps(
                {
                    "executive_summary": "One synthetic persona; Lena Vogel values same-day booking. No interviews or evidence yet.",
                    "key_findings": ["Finding 1 with concrete data", "Lena books services from her phone.", "Finding 2"],
                    "recommendations": ["Recommendation 1", "Recommendation 2"],
                    "major_risks": ["Risk 1", "Winter demand may drop"],
                    "strongest_segments": ["Segment A"],
                    "evidence_findings": [{"title": "...", "claim": "...", "confidence": 0.9, "source": "..."}],
                    "target_market_summary": "Detailed target market overview",
                    "market_context_summary": "Berlin has roughly 100,000 registered dogs; most owners work full time.",
                }
            )
        ],
    )

    res = api_test_app.post(f"/api/studies/{study_id}/reports/generate", json={}, headers=auth_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["key_findings"] == ["Lena books services from her phone."]
    assert body["recommendations"] == [] and body["strongest_segments"] == []
    assert body["major_risks"] == ["Winter demand may drop"]
    assert body["evidence_findings"] == []
    assert body["target_market_summary"] is None
    assert body["market_context_summary"].startswith("Berlin has roughly")
