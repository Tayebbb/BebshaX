"""Memory listing requires private ownership independently of shared persona visibility."""

from datetime import datetime, timedelta, timezone

import pytest

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations
from bebshax.memory.orm import MemoryItems


@pytest.fixture
async def exhibition_memory_case(api_test_app):
    owner = Users(id="exhibition_mem_owner", email="mem-owner@example.test", full_name="Memory Owner", is_verified=True)
    visitor = Users(id="exhibition_mem_visitor", email="mem-visitor@example.test", full_name="Memory Visitor", is_verified=True)
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
        records = [("baseline", None, "persona", "semantic", None)]
        records.extend(
            (f"{caller}_{source}", f"exhibition_mem_{caller}_conversation", source, "episodic", user_id)
            for caller, user_id in [("public", None), ("owner", owner.id), ("visitor", visitor.id)]
            for source in ["persona", "interviewer", "system"]
        )
        records.extend([
            ("orphan", "exhibition_mem_missing_conversation", "persona", "episodic", None),
            ("wrong_persona", "exhibition_mem_wrong_persona_conversation", "persona", "episodic", None),
        ])
        session.add_all([
            MemoryItems(
                id=f"exhibition_mem_{name}", persona_id="exhibition_mem_shared",
                owner_id=memory_owner,
                kind=kind, text=f"{name}-memory-marker", source=source,
                conversation_id=conversation_id, embedding=[0.0] * 384,
                embedding_space="privacy-fixture", created_at=base_time + timedelta(seconds=index),
            )
            for index, (name, conversation_id, source, kind, memory_owner) in enumerate(records)
        ])
        await session.commit()
    yield api_test_app, {"owner": owner, "visitor": visitor, "anonymous": None}


@pytest.mark.parametrize("caller", ["anonymous", "owner", "visitor"])
@pytest.mark.parametrize("include_interviewer", [False, True])
def test_memory_list_scopes_every_source_to_readable_conversations(
    exhibition_memory_case, caller, include_interviewer
):
    client, users = exhibition_memory_case
    headers = {"Authorization": f"Bearer {create_access_token(users[caller].id)}"} if users[caller] else {}

    response = client.get(
        "/api/personas/exhibition_mem_shared/memories",
        params={"include_interviewer": include_interviewer},
        headers=headers,
    )

    if caller == "anonymous":
        assert response.status_code == 401
        return
    assert response.status_code == 200, response.text
    visible_callers = [caller]
    sources = ["persona", "interviewer", "system"] if include_interviewer else ["persona"]
    expected = {
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
    headers = {"Authorization": f"Bearer {create_access_token(users[caller].id)}"} if users[caller] else {}

    response = client.get(
        "/api/personas/exhibition_mem_shared/memories",
        params={"limit": 1, "include_interviewer": include_interviewer, "kind": "episodic"},
        headers=headers,
    )

    if caller == "anonymous":
        assert response.status_code == 401
        return
    assert response.status_code == 200, response.text
    visible_caller = caller
    source = "system" if include_interviewer else "persona"
    assert [item["id"] for item in response.json()] == [f"exhibition_mem_{visible_caller}_{source}"]


@pytest.mark.parametrize("caller, expected_status", [("anonymous", 401), ("visitor", 404), ("owner", 200)])
def test_memory_list_keeps_persona_ownership_gate(exhibition_memory_case, caller, expected_status):
    client, users = exhibition_memory_case
    headers = {"Authorization": f"Bearer {create_access_token(users[caller].id)}"} if users[caller] else {}

    response = client.get("/api/personas/exhibition_mem_owned/memories?include_interviewer=true", headers=headers)

    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert response.json() == []