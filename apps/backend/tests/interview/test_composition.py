from bebshax.interview.engine import InterviewEngine, build_identity_card


def test_identity_card_contains_all_identity_fields(stored_persona) -> None:
    card = build_identity_card(stored_persona)
    for expected in ("Rina Akter", "24", "university student", "Dhaka", "student stipend"):
        assert expected in card
    assert "goal: find affordable meal deals" in card
    assert "pain point: late deliveries" in card


def test_identity_card_is_deterministic(stored_persona) -> None:
    assert build_identity_card(stored_persona) == build_identity_card(stored_persona)


async def test_composition_places_identity_history_and_message(
    session_maker, stored_persona, memory_service, llm_factory
) -> None:
    llm, adapter = llm_factory(["reply one", "reply two"])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "learn about delivery pain points")

    await engine.ask(conversation.id, "How often do you order food online?")
    await engine.ask(conversation.id, "What annoys you about it?")

    second_request = adapter.requests[1]
    system = second_request.messages[0]
    assert system.role == "system"
    assert "Rina Akter" in system.content  # identity present every turn
    assert "INTERVIEW OBJECTIVE: learn about delivery pain points" in system.content
    assert "QuickBite" in system.content  # business context present

    # full history: system, q1, a1, q2
    roles = [m.role for m in second_request.messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert second_request.messages[1].content == "How often do you order food online?"
    assert second_request.messages[2].content == "reply one"
    assert second_request.messages[3].content == "What annoys you about it?"
