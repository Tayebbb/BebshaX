import asyncio
import json
import logging

import pytest
from sqlalchemy import select

import bebshax.interview.engine as interview_engine
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


@pytest.mark.parametrize("streaming", [False, True], ids=["ask", "stream"])
@pytest.mark.parametrize("blocked", [False, True], ids=["fast-suggestions", "blocked-suggestions"])
async def test_optional_suggestions_preserve_answer_when_fast_or_blocked(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch, caplog,
    streaming, blocked,
) -> None:
    reply = "I usually skip breakfast because the canteen opens late."
    question = "Tell me about your mornings."
    suggestions = ["What happens when the canteen opens on time?"]
    llm, adapter = llm_factory([reply, json.dumps(suggestions)])
    engine = InterviewEngine(llm, session_maker, memory=memory_service, suggest_questions=True)
    conversation = await engine.start(stored_persona.id, "breakfast habits")
    suggestion_started = asyncio.Event()
    suggestion_cancelled = asyncio.Event()
    original_complete = adapter.complete

    async def complete_with_blocked_suggestions(candidate, request):
        if blocked and request.task == TaskType.STRUCTURED_OUTPUT:
            suggestion_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                suggestion_cancelled.set()
                raise
        return await original_complete(candidate, request)

    monkeypatch.setattr(adapter, "complete", complete_with_blocked_suggestions)
    monkeypatch.setattr(interview_engine, "_SUGGESTED_QUESTIONS_TIMEOUT_SECONDS", 0.05, raising=False)

    async def get_answer():
        if streaming:
            events = [event async for event in engine.ask_stream(conversation.id, question)]
            assert events[0]["type"] == "delta"
            assert events[-1]["type"] == "done"
            return events[-1]
        return await engine.ask(conversation.id, question)

    with caplog.at_level(logging.INFO, logger=interview_engine.__name__):
        answer_task = asyncio.create_task(get_answer())
        try:
            if blocked:
                await asyncio.wait_for(suggestion_started.wait(), timeout=5)
            result = await asyncio.wait_for(answer_task, timeout=1)
        finally:
            if not answer_task.done():
                answer_task.cancel()
            await asyncio.gather(answer_task, return_exceptions=True)

    assert result["reply"] == reply
    assert result["served_by"] == "fake/m1"
    assert result["turn_number"] == 2
    assert result["suggested_questions"] == ([] if blocked else suggestions)
    assert suggestion_cancelled.is_set() is blocked
    timeout_logs = [
        record.getMessage() for record in caplog.records
        if record.name == interview_engine.__name__ and "timed out" in record.getMessage()
    ]
    assert bool(timeout_logs) is blocked
    assert all(reply not in message and question not in message for message in timeout_logs)

    _, turns = await engine.transcript(conversation.id)
    assert [turn.content for turn in turns] == [question, reply]
    async with session_maker() as session:
        memories = list((await session.execute(
            select(MemoryItems).where(MemoryItems.conversation_id == conversation.id)
        )).scalars())
    assert sorted((memory.source, memory.text) for memory in memories) == [
        ("interviewer", question), ("persona", reply),
    ]
