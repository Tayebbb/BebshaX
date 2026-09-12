"""Detail refreshes return persisted data without invoking the LLM service."""

import json
from unittest.mock import AsyncMock

import pytest

from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm.types import TaskType


@pytest.mark.parametrize(
    ("turn_metadata", "configuration", "expected"),
    [
        pytest.param(
            [
                {"suggested_questions": ["Earlier follow-up?"]},
                {"suggested_questions": ["Latest follow-up?", "What changed?"]},
            ],
            {"suggested_questions": ["Configuration follow-up?"]},
            ["Latest follow-up?", "What changed?"],
            id="newest-turn-wins",
        ),
        pytest.param(
            [{"suggested_questions": ["Saved follow-up?"]}, {}],
            {},
            ["Saved follow-up?"],
            id="newest-metadata-with-suggestions",
        ),
        pytest.param(
            [{}],
            {"suggested_questions": ["Configuration follow-up?"]},
            ["Configuration follow-up?"],
            id="configuration-fallback",
        ),
        pytest.param(
            [
                {"suggested_questions": ["Earlier follow-up?"]},
                {"suggested_questions": []},
            ],
            {"suggested_questions": ["Configuration follow-up?"]},
            [],
            id="explicit-empty-turn-wins",
        ),
        pytest.param([{}], {}, [], id="legacy-transcript"),
        pytest.param([], {}, [], id="legacy-empty-conversation"),
    ],
)
async def test_detail_refresh_never_calls_llm(
    api_test_app, auth_headers, monkeypatch, turn_metadata, configuration, expected
) -> None:
    client = api_test_app
    study_id = "study_read_latency"
    interview_id = "interview_read_latency"
    persona_id = "persona_read_latency"
    owner_id = "usr_test_fixture"
    memories = [{"id": "memory_saved", "text": "Previously saved evidence"}]
    provenance = {"request_id": "request_saved", "provider": "fake", "model": "m1"}
    stored_metadata = [
        {"provenance": provenance, **metadata} for metadata in turn_metadata
    ]

    async with client.app.state.db_sessionmaker() as session:
        session.add(Studies(id=study_id, user_id=owner_id, title="Read latency"))
        session.add(Personas(
            id=persona_id, study_id=study_id, owner_id=owner_id, name="Synthetic Participant"
        ))
        await session.flush()
        session.add(Conversations(
            id=interview_id, study_id=study_id, user_id=owner_id,
            persona_id=persona_id, objective="Understand delivery decisions",
            configuration=configuration, turn_count=len(stored_metadata),
        ))
        await session.flush()
        for turn_number, metadata in enumerate(stored_metadata, start=1):
            session.add(ConversationTurns(
                id=f"read_turn_{turn_number}", conversation_id=interview_id,
                turn_number=turn_number, role="persona", content=f"Saved reply {turn_number}",
                served_by="fake/m1", latency_ms=12.5,
                retrieved_memories=memories, metadata_json=metadata,
            ))
        session.add(InterviewInsights(
            id="insight_read_latency", interview_id=interview_id, study_id=study_id,
            user_id=owner_id, persona_id=persona_id, type="need",
            title="Saved insight", description="Saved description",
        ))
        await session.commit()

    refusing_complete = AsyncMock(side_effect=AssertionError("GET must never call an LLM"))
    monkeypatch.setattr(client.app.state.interview_engine._llm, "complete", refusing_complete)

    for _refresh in range(2):
        response = client.get(
            f"/api/studies/{study_id}/interviews/{interview_id}", headers=auth_headers
        )
        assert response.status_code == 200
        refusing_complete.assert_not_awaited()
        detail = response.json()
        assert detail["suggested_questions"] == expected
        assert detail["configuration"] == configuration
        assert detail["turn_count"] == len(stored_metadata)
        assert detail["structured_insights"][0]["id"] == "insight_read_latency"
        assert [turn["content"] for turn in detail["turns"]] == [
            f"Saved reply {number}" for number in range(1, len(stored_metadata) + 1)
        ]
        assert [turn["metadata"] for turn in detail["turns"]] == stored_metadata
        for turn in detail["turns"]:
            assert turn["retrieved_memories"] == memories
            assert turn["served_by"] == "fake/m1"
            assert turn["latency_ms"] == 12.5


@pytest.mark.parametrize(
    "questions",
    [
        pytest.param(["What happened next?", "How did that affect your plans?"], id="generated"),
        pytest.param([], id="explicit-empty-replaces-saved"),
    ],
)
async def test_post_defers_generated_suggestions_and_preserves_detail_refresh(
    api_test_app, auth_headers, monkeypatch, questions
) -> None:
    client = api_test_app
    study_id = "study_post_read_latency"
    interview_id = "interview_post_read_latency"
    persona_id = "persona_post_read_latency"
    previous_question = "How do you arrange deliveries?"
    previous_reply = "I arrange deliveries around my working day."
    question = "Tell me about your most recent delivery."
    reply = (
        "I waited at home for the delivery yesterday. It arrived later than expected, "
        "so I had to rearrange my plans for the afternoon."
    )

    async with client.app.state.db_sessionmaker() as session:
        session.add(Studies(id=study_id, user_id="usr_test_fixture", title="Post then refresh"))
        session.add(Personas(
            id=persona_id, study_id=study_id, owner_id="usr_test_fixture",
            name="Synthetic Participant", demographics={"occupation": "Office worker"},
        ))
        await session.flush()
        session.add(Conversations(
            id=interview_id, study_id=study_id, user_id="usr_test_fixture",
            persona_id=persona_id, objective="Understand delivery decisions",
            turn_count=2, question_count=1,
            configuration={"suggested_questions": ["Stale configuration follow-up?"]},
        ))
        await session.flush()
        session.add_all([
            ConversationTurns(
                id="post_read_previous_question", conversation_id=interview_id,
                turn_number=1, role="interviewer", content=previous_question,
            ),
            ConversationTurns(
                id="post_read_previous_reply", conversation_id=interview_id,
                turn_number=2, role="persona", content=previous_reply,
                metadata_json={"suggested_questions": ["Stale turn follow-up?"]},
            ),
        ])
        await session.commit()

    engine = client.app.state.interview_engine
    monkeypatch.setattr(engine, "_suggest_questions", True)
    adapter = client.app.state.llm_adapters["pollinations"]
    route = adapter._routes[("pollinations", "deepseek-r1")]
    monkeypatch.setattr(route, "replies", [reply, json.dumps({"questions": questions})])
    complete = AsyncMock(wraps=engine._llm.complete)
    monkeypatch.setattr(engine._llm, "complete", complete)
    calls_before = len(adapter.calls)
    requests_before = len(adapter.requests)

    response = client.post(
        f"/api/studies/{study_id}/interviews/{interview_id}/messages",
        json={"content": question}, headers=auth_headers,
    )
    assert response.status_code == 200
    posted = response.json()
    assert posted["reply"] == reply
    assert posted["turn_number"] == 4
    assert posted["turn_count"] == 4
    assert posted["served_by"] == "pollinations/deepseek-r1"
    assert posted["suggested_questions"] == []
    assert complete.await_count == 1
    assert adapter.calls[calls_before:] == ["pollinations/deepseek-r1"]
    requests = adapter.requests[requests_before:]
    assert [request.task for request in requests] == [
        TaskType.PERSONA_INTERVIEW,
    ]
    primary_context = "\n".join(message.content for message in requests[0].messages)
    for content in (previous_question, previous_reply, question):
        assert content in primary_context

    for _refresh in range(2):
        response = client.get(
            f"/api/studies/{study_id}/interviews/{interview_id}", headers=auth_headers
        )
        assert response.status_code == 200
        detail = response.json()
        assert detail["suggested_questions"] == []
        assert detail["turn_count"] == 4
        assert [turn["turn_number"] for turn in detail["turns"]] == [1, 2, 3, 4]
        assert [turn["content"] for turn in detail["turns"]] == [
            previous_question, previous_reply, question, reply,
        ]
        persona_turn = detail["turns"][-1]
        assert persona_turn["role"] == "persona"
        assert persona_turn["metadata"]["suggested_questions"] == []
        assert persona_turn["served_by"] == posted["served_by"]
        assert persona_turn["latency_ms"] == posted["latency_ms"]
        assert complete.await_count == 1
        assert len(adapter.calls) == calls_before + 1