"""Memory listing must authorize the conversation as well as its shared persona."""

from datetime import datetime, timedelta, timezone

import pytest

from bebshax.api.auth import get_optional_current_user
from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations
from bebshax.memory.orm import MemoryItems


@pytest.fixture
async def exhibition_memory_case(api_test_app):
    owner = Users(id="exhibition_mem_owner", email="mem-owner@example.test", full_name="Memory Owner")
    visitor = Users(id="exhibition_mem_visitor", email="mem-visitor@example.test", full_name="Memory Visitor")
    async with api_test_app.app.state.db_sessionmaker() as session:
        session.add_all([owner, visitor])
        await session.flush()
        session.add(Studies(
            id="exhibition_mem_study", title="Public memory fixture",
            user_id="usr_system_holder", is_demo=True,
        ))
        await session.flush()
        session.add_all([
            Personas(id="exhibition_mem_shared", name="Shared Persona", study_id="exhibition_mem_study"),
            Personas(id="exhibition_mem_owned", name="Private Persona", owner_id=owner.id),
        ])
        await session.flush()
        session.add_all([
            Conversations(
                id=f"exhibition_mem_{caller}_conversation",
                study_id="exhibition_mem_study",
                persona_id="exhibition_mem_shared",
                user_id=user_id,
                objective=f"{caller} interview",
            )
            for caller, user_id in [("public", None), ("owner", owner.id), ("visitor", visitor.id)]
        ])
        session.add(Conversations(
            id="exhibition_mem_wrong_persona_conversation",
            persona_id="exhibition_mem_owned", user_id=None, objective="Different persona",
        ))
        await session.flush()
        base_time = datetime(2026, 9, 9, tzinfo=timezone.utc)
        records = [("baseline", None, "persona", "semantic")]
        records.extend(
            (f"{caller}_{source}", f"exhibition_mem_{caller}_conversation", source, "episodic")
            for caller in ["public", "owner", "visitor"]
            for source in ["persona", "interviewer", "system"]
        )
        records.extend([
            ("orphan", "exhibition_mem_missing_conversation", "persona", "episodic"),
            ("wrong_persona", "exhibition_mem_wrong_persona_conversation", "persona", "episodic"),
        ])
        session.add_all([
            MemoryItems(
                id=f"exhibition_mem_{name}", persona_id="exhibition_mem_shared",
                kind=kind, text=f"{name}-memory-marker", source=source,
                conversation_id=conversation_id, embedding=[0.0] * 384,
                embedding_space="privacy-fixture", created_at=base_time + timedelta(seconds=index),
            )
            for index, (name, conversation_id, source, kind) in enumerate(records)
        ])
        await session.commit()
    yield api_test_app, {"owner": owner, "visitor": visitor, "anonymous": None}
    api_test_app.app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.mark.parametrize("caller", ["anonymous", "owner", "visitor"])
@pytest.mark.parametrize("include_interviewer", [False, True])
def test_memory_list_scopes_every_source_to_readable_conversations(
    exhibition_memory_case, caller, include_interviewer
):
    client, users = exhibition_memory_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get(
        "/api/personas/exhibition_mem_shared/memories",
        params={"include_interviewer": include_interviewer},
    )

    assert response.status_code == 200, response.text
    visible_callers = ["public"] + ([caller] if caller != "anonymous" else [])
    sources = ["persona", "interviewer", "system"] if include_interviewer else ["persona"]
    expected = {"exhibition_mem_baseline"} | {
        f"exhibition_mem_{visible_caller}_{source}"
        for visible_caller in visible_callers
        for source in sources
    }
    assert {item["id"] for item in response.json()} == expected
    assert all(item["persona_id"] == "exhibition_mem_shared" for item in response.json())


@pytest.mark.parametrize("caller", ["anonymous", "owner", "visitor"])
@pytest.mark.parametrize("include_interviewer", [False, True])
def test_memory_visibility_is_applied_before_limit(exhibition_memory_case, caller, include_interviewer):
    client, users = exhibition_memory_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get(
        "/api/personas/exhibition_mem_shared/memories",
        params={"limit": 1, "include_interviewer": include_interviewer, "kind": "episodic"},
    )

    assert response.status_code == 200, response.text
    visible_caller = "public" if caller == "anonymous" else caller
    source = "system" if include_interviewer else "persona"
    assert [item["id"] for item in response.json()] == [f"exhibition_mem_{visible_caller}_{source}"]


@pytest.mark.parametrize("caller, expected_status", [("anonymous", 404), ("visitor", 404), ("owner", 200)])
def test_memory_list_keeps_persona_ownership_gate(exhibition_memory_case, caller, expected_status):
    client, users = exhibition_memory_case
    client.app.dependency_overrides[get_optional_current_user] = lambda: users[caller]

    response = client.get("/api/personas/exhibition_mem_owned/memories?include_interviewer=true")

    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert response.json() == []