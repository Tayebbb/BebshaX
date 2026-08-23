import pytest
from sqlalchemy import func, select

from bebshax.interview.engine import ConversationNotFound, InterviewEngine, PersonaNotFound
from bebshax.llm import TaskType
from bebshax.memory.orm import MemoryItems


async def test_multi_turn_stability_and_transcript(
    session_maker, stored_persona, memory_service, llm_factory
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
    # memories may evolve turn to turn, the identity never does
    from bebshax.interview.engine import build_identity_card

    card = build_identity_card(stored_persona)
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
        count = (
            await session.execute(
                select(func.count()).select_from(MemoryItems).where(
                    MemoryItems.persona_id == stored_persona.id,
                    MemoryItems.kind == "episodic",
                )
            )
        ).scalar()
    assert count == 2


async def test_unknown_ids_raise(session_maker, stored_persona, memory_service, llm_factory) -> None:
    llm, _ = llm_factory([])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    with pytest.raises(PersonaNotFound):
        await engine.start("missing", "obj")
    with pytest.raises(ConversationNotFound):
        await engine.ask("missing", "q")
    with pytest.raises(ConversationNotFound):
        await engine.transcript("missing")
