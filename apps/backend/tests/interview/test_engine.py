import pytest
from sqlalchemy import select

from bebshax.interview.engine import ConversationNotFound, InterviewEngine, PersonaNotFound
from bebshax.llm import TaskType
from bebshax.memory.orm import MemoryItems


async def test_multi_turn_stability_and_transcript(
    session_maker, stored_persona, stored_persona_card, memory_service, llm_factory
) -> None:
    llm, adapter = llm_factory(["I'm Rina!", "I'm 24.", "I study at university."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "identity check")

    for question in ("What's your name?", "How old are you?", "What do you do?"):
        result = await engine.ask(conversation.id, question)
        assert result["reply"]

    # every request used PERSONA_INTERVIEW with the conversation id attached
    assert all(r.task == TaskType.PERSONA_INTERVIEW for r in adapter.requests)
    assert all(r.conversation_id == conversation.id for r in adapter.requests)
    # the identity card is byte-identical inside every turn's system message —
    # memories may evolve turn to turn, the identity never does. The card is the
    # one built from the stored Personas row (save_persona mirrors the profile).
    card = stored_persona_card
    assert "Rina Akter" in card and "Occupation: university student" in card
    assert all(card in r.messages[0].content for r in adapter.requests)

    _, turns = await engine.transcript(conversation.id)
    assert [t.turn_number for t in turns] == [1, 2, 3, 4, 5, 6]
    assert [t.role for t in turns] == ["interviewer", "persona"] * 3


async def test_each_exchange_writes_an_observation_memory(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    llm, _ = llm_factory(["a", "b"])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "obj")
    await engine.ask(conversation.id, "q1")
    await engine.ask(conversation.id, "q2")

    async with session_maker() as session:
        rows = list(
            (
                await session.execute(
                    select(MemoryItems).where(
                        MemoryItems.persona_id == stored_persona.id,
                        MemoryItems.kind == "episodic",
                    )
                )
            ).scalars()
        )
    # one persona-sourced recollection per exchange (the reply, full text) plus
    # one interviewer-sourced audit item (the question) — never merged into one
    assert sorted(r.text for r in rows if r.source == "persona") == ["a", "b"]
    assert sorted(r.text for r in rows if r.source == "interviewer") == ["q1", "q2"]
    assert all(r.conversation_id == conversation.id for r in rows)


async def test_unknown_ids_raise(session_maker, stored_persona, memory_service, llm_factory) -> None:
    llm, _ = llm_factory([])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    with pytest.raises(PersonaNotFound):
        await engine.start("missing", "obj")
    with pytest.raises(ConversationNotFound):
        await engine.ask("missing", "q")
    with pytest.raises(ConversationNotFound):
        await engine.transcript("missing")


async def test_suggested_questions_are_model_written_from_the_transcript(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    """With suggestions enabled the engine asks the model for follow-ups built
    on THIS transcript; an unusable reply yields no suggestions (never a canned
    pool)."""
    import json

    llm, adapter = llm_factory([
        "I usually skip breakfast because the canteen opens late.",
        json.dumps(["What happens on days the canteen opens on time?", "How much does a typical breakfast cost you?"]),
        "I pay about 60 taka when I do eat.",
        "not json",
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service, suggest_questions=True)
    conversation = await engine.start(stored_persona.id, "breakfast habits")

    first = await engine.ask(conversation.id, "Tell me about your mornings.")
    assert first["suggested_questions"] == [
        "What happens on days the canteen opens on time?",
        "How much does a typical breakfast cost you?",
    ]
    suggestion_request = adapter.requests[1]
    assert suggestion_request.task == TaskType.STRUCTURED_OUTPUT
    prompt = suggestion_request.messages[-1].content
    assert "INTERVIEW_STATE" in prompt and "skip breakfast" in prompt
    assert "topics_not_yet_explored" in prompt

    second = await engine.ask(conversation.id, "What does it cost?")
    assert second["suggested_questions"] == []  # unusable reply -> nothing substituted

    # Disabled engines never spend a call on suggestions.
    quiet_llm, quiet_adapter = llm_factory(["reply"])
    quiet = InterviewEngine(quiet_llm, session_maker, memory=memory_service)
    conv2 = await quiet.start(stored_persona.id, "x")
    res = await quiet.ask(conv2.id, "q")
    assert res["suggested_questions"] == [] and len(quiet_adapter.requests) == 1
