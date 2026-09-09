"""API privacy regressions for private interviews beneath shared studies."""

import json
from unittest.mock import AsyncMock

import pytest

from bebshax.api.auth import get_optional_current_user
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.engine import InterviewConflict
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.utils.explicit_failures import UnusableModelOutput


@pytest.fixture
async def exhibition_privacy_case(api_test_app, monkeypatch):
    owner = Users(
        id="exhibition_privacy_owner",
        email="privacy-owner@example.test",
        full_name="Privacy Owner",
        is_active=True,
    )
    visitor = Users(
        id="exhibition_privacy_visitor",
        email="privacy-visitor@example.test",
        full_name="Privacy Visitor",
        is_active=True,
    )
    async with api_test_app.app.state.db_sessionmaker() as session:
        session.add_all([owner, visitor])
        await session.flush()
        session.add(Studies(
            id="exhibition_privacy_study",
            user_id="usr_system_holder",
            title="Shared privacy fixture",
            prompt="Synthetic research fixture",
            is_demo=True,
        ))
        await session.flush()
        session.add(Personas(
            id="exhibition_privacy_persona",
            name="Shared Synthetic Persona",
            study_id="exhibition_privacy_study",
            owner_id=None,
        ))
        session.add(Personas(
            id="exhibition_privacy_legacy_persona",
            name="Shared Legacy Persona",
            owner_id=None,
        ))
        await session.flush()
        session.add(Conversations(
            id="exhibition_privacy_conversation",
            study_id="exhibition_privacy_study",
            persona_id="exhibition_privacy_persona",
            user_id=owner.id,
            objective="private-objective-marker",
            turn_count=1,
            question_count=1,
        ))
        session.add_all([
            Conversations(
                id="exhibition_privacy_public_conversation",
                study_id="exhibition_privacy_study",
                persona_id="exhibition_privacy_persona",
                user_id=None,
                objective="Public example",
                status="completed",
            ),
            Conversations(
                id="exhibition_privacy_other_study_conversation",
                study_id="exhibition_privacy_other_study",
                persona_id="exhibition_privacy_persona",
                user_id=None,
                objective="Unrelated study example",
            ),
            Conversations(
                id="exhibition_privacy_legacy_conversation",
                persona_id="exhibition_privacy_legacy_persona",
                user_id=None,
                objective="Public legacy example",
            ),
        ])
        await session.flush()
        session.add(ConversationTurns(
            id="exhibition_privacy_turn",
            conversation_id="exhibition_privacy_conversation",
            turn_number=1,
            role="researcher",
            content="private-transcript-marker",
        ))
        session.add_all([
            InterviewInsights(
                id=f"exhibition_privacy_insight_{suffix}",
                interview_id=conversation_id,
                study_id="exhibition_privacy_study",
                persona_id="exhibition_privacy_persona",
                user_id=insight_owner,
                type="need",
                title=f"{suffix}-insight-marker",
                description=f"{suffix}-insight-detail-marker",
            )
            for suffix, conversation_id, insight_owner in [
                ("private", "exhibition_privacy_conversation", owner.id),
                ("public", "exhibition_privacy_public_conversation", None),
                ("mismatched", "exhibition_privacy_other_study_conversation", None),
            ]
        ])
        await session.commit()
    monkeypatch.setattr(
        api_test_app.app.state.interview_engine,
        "generate_suggested_questions",
        AsyncMock(return_value=[]),
    )
    yield api_test_app, {"owner": owner, "visitor": visitor, "anonymous": None}
    api_test_app.app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.mark.parametrize("caller", ["anonymous", "visitor"])
@pytest.mark.parametrize("suffix", ["", "/insights"])
def test_shared_study_private_interview_is_not_readable(exhibition_privacy_case, caller, suffix):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get(
        f"/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation{suffix}"
    )

    assert response.status_code == 403, response.text
    assert "private-transcript-marker" not in response.text


def test_shared_study_private_interview_remains_readable_to_owner(exhibition_privacy_case):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users["owner"]

    response = client.get(
        "/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation"
    )

    assert response.status_code == 200, response.text
    assert response.json()["turns"][0]["content"] == "private-transcript-marker"


@pytest.mark.parametrize("caller, expected_total", [("anonymous", 1), ("visitor", 1), ("owner", 2)])
def test_shared_study_interview_list_filters_private_children(
    exhibition_privacy_case, caller, expected_total
):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get("/api/studies/exhibition_privacy_study/interviews")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == expected_total
    expected_ids = {"exhibition_privacy_public_conversation"}
    if caller == "owner":
        expected_ids.add("exhibition_privacy_conversation")
    assert {item["id"] for item in response.json()["interviews"]} == expected_ids


@pytest.mark.parametrize("caller, expected_total", [("anonymous", 1), ("visitor", 1), ("owner", 2)])
def test_shared_study_metrics_filter_private_and_mismatched_children(
    exhibition_privacy_case, caller, expected_total
):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get("/api/studies/exhibition_privacy_study/interviews/metrics")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "study_id": "exhibition_privacy_study",
        "total_interviews": expected_total,
        "active_interviews": expected_total - 1,
        "completed_interviews": 1,
        "total_insights_generated": expected_total,
    }


@pytest.mark.parametrize("caller", ["anonymous", "visitor", "owner"])
@pytest.mark.parametrize("is_demo", [True, False])
@pytest.mark.parametrize("route", ["/api/conversations", "/api/personas/{persona_id}/conversations"])
async def test_legacy_aliases_cannot_create_interviews_in_shared_studies(
    exhibition_privacy_case, monkeypatch, caller, is_demo, route
):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]
    async with client.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, "exhibition_privacy_study")
        study.is_demo = is_demo
        study.user_id = "usr_system_holder" if is_demo else "usr_default"
        await session.commit()
    engine = client.app.state.interview_engine
    start = AsyncMock(wraps=engine.start)
    monkeypatch.setattr(engine, "start", start)

    response = client.post(
        route.format(persona_id="exhibition_privacy_persona"),
        json={"persona_id": "exhibition_privacy_persona", "objective": "Unauthorized interview"},
    )

    assert response.status_code == 403, response.text
    start.assert_not_awaited()


@pytest.mark.parametrize("route", ["/api/conversations", "/api/personas/{persona_id}/conversations"])
@pytest.mark.parametrize("caller, expected_status", [("anonymous", 403), ("owner", 201)])
async def test_legacy_no_study_creation_requires_a_private_owner(
    exhibition_privacy_case, route, caller, expected_status
):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.post(
        route.format(persona_id="exhibition_privacy_legacy_persona"),
        json={"persona_id": "exhibition_privacy_legacy_persona", "objective": "Private legacy interview"},
    )

    assert response.status_code == expected_status, response.text
    if expected_status == 201:
        async with client.app.state.db_sessionmaker() as session:
            conversation = await session.get(Conversations, response.json()["id"])
            assert conversation.user_id == users["owner"].id
            assert conversation.study_id is None
        client.app.dependency_overrides[get_optional_current_user] = lambda: users["visitor"]
        assert client.get(f"/api/conversations/{response.json()['id']}").status_code == 404


@pytest.mark.parametrize("caller", ["anonymous", "visitor", "owner"])
def test_legacy_no_study_shared_transcript_stays_readable(exhibition_privacy_case, caller):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get("/api/conversations/exhibition_privacy_legacy_conversation")

    assert response.status_code == 200, response.text
    assert response.json()["objective"] == "Public legacy example"


@pytest.mark.parametrize("caller", ["anonymous", "visitor"])
def test_legacy_alias_cannot_read_a_private_child_of_a_shared_study(exhibition_privacy_case, caller):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get("/api/conversations/exhibition_privacy_conversation")

    assert response.status_code == 404, response.text
    assert "private-objective-marker" not in response.text


@pytest.mark.parametrize("route, method", [
    ("/api/conversations/exhibition_privacy_conversation/messages", "ask"),
    ("/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation/messages", "ask"),
    ("/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation/messages/stream", "ask_stream"),
    ("/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation/complete", "complete"),
])
def test_owner_of_old_private_child_cannot_mutate_shared_study(
    exhibition_privacy_case, monkeypatch, route, method
):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users["owner"]
    engine = client.app.state.interview_engine
    operation = AsyncMock(wraps=getattr(engine, method))
    remember = AsyncMock(wraps=client.app.state.memory_service.remember)
    monkeypatch.setattr(engine, method, operation)
    monkeypatch.setattr(client.app.state.memory_service, "remember", remember)

    response = client.post(route, json={"message": "Do not store this in the shared persona"})

    assert response.status_code == 403, response.text
    operation.assert_not_called()
    remember.assert_not_awaited()


@pytest.fixture
async def exhibition_owned_interview(exhibition_privacy_case):
    client, users = exhibition_privacy_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users["owner"]
    async with client.app.state.db_sessionmaker() as session:
        study = await session.get(Studies, "exhibition_privacy_study")
        study.is_demo = False
        study.user_id = users["owner"].id
        persona = await session.get(Personas, "exhibition_privacy_persona")
        persona.owner_id = users["owner"].id
        await session.commit()
    return client


async def test_stream_preserves_real_persona_version_conflict(exhibition_owned_interview):
    client = exhibition_owned_interview
    async with client.app.state.db_sessionmaker() as session:
        persona = await session.get(Personas, "exhibition_privacy_persona")
        persona.version = 2
        await session.commit()

    response = client.post(
        "/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation/messages/stream",
        json={"message": "Question after persona regeneration"},
    )

    assert response.status_code == 200, response.text
    assert response.text.count("event: error") == 1
    assert "event: done" not in response.text
    assert "event: delta" not in response.text
    payload = json.loads(response.text.split("data: ", 1)[1].strip())
    assert payload["kind"] == "conflict"
    assert payload["error_code"] == "persona_version_conflict"
    assert payload["status_code"] == 409
    assert payload["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("failure, expected_kind", [
    (InterviewConflict("This interview is already processing a turn."), "conflict"),
    (UnusableModelOutput("interview_reply_unusable", "The reply could not be used.", attempts=2), "explicit_failure"),
])
def test_stream_preserves_explicit_failure_after_delta(
    exhibition_owned_interview, monkeypatch, failure, expected_kind
):
    client = exhibition_owned_interview

    async def failed_stream(*args, **kwargs):
        yield {"type": "delta", "text": "Partial response"}
        raise failure

    monkeypatch.setattr(client.app.state.interview_engine, "ask_stream", failed_stream)

    response = client.post(
        "/api/studies/exhibition_privacy_study/interviews/exhibition_privacy_conversation/messages/stream",
        json={"message": "A synthetic interview question"},
    )

    assert response.status_code == 200, response.text
    assert response.text.count("event: delta") == 1
    assert response.text.count("event: error") == 1
    assert "event: done" not in response.text
    payload = json.loads(response.text.split("event: error\ndata: ", 1)[1].strip())
    assert payload["kind"] == expected_kind
    assert payload["error_code"] == failure.error_code
    assert payload["status_code"] == failure.status_code
    assert payload["detail"] == failure.detail
    assert payload["request_id"] == response.headers["x-request-id"]
    for key, value in failure.extra.items():
        assert payload[key] == value