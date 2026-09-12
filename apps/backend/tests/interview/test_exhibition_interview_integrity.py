"""Offline regressions for interview context integrity and atomic state changes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import MarketSegments, Personas
from bebshax.interview.engine import InterviewEngine, InterviewFinished
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm import LLMRequest, LLMService, TaskType
from bebshax.llm.adapters.base import AdapterCompletion, RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryRecord, MemoryService
from bebshax.persona.schema import PersonaProfile
from bebshax.utils.explicit_failures import ExplicitFailure


LLMFactory = Callable[[list[str]], tuple[LLMService, FakeAdapter]]


async def _roomy_llm(
    llm_factory: LLMFactory, replies: list[str]
) -> tuple[LLMService, FakeAdapter]:
    llm, adapter = llm_factory(replies)
    for candidate in await adapter.candidates():
        candidate.context_window = 1_000_000
    return llm, adapter


async def _persisted_state(
    session_maker: sessionmaker[AsyncSession], conversation: Conversations
) -> dict[str, Any]:
    async with session_maker() as session:
        conversation_row = (
            await session.execute(
                select(Conversations.__table__).where(Conversations.id == conversation.id)
            )
        ).mappings().one()
        turn_rows = (
            await session.execute(
                select(ConversationTurns.__table__)
                .where(ConversationTurns.conversation_id == conversation.id)
                .order_by(ConversationTurns.turn_number)
            )
        ).mappings().all()
        memory_rows = (
            await session.execute(
                select(MemoryItems.__table__)
                .where(MemoryItems.persona_id == conversation.persona_id)
                .order_by(MemoryItems.id)
            )
        ).mappings().all()
    return {
        "conversation": dict(conversation_row),
        "turns": [dict(row) for row in turn_rows],
        "memories": [dict(row) for row in memory_rows],
    }


@pytest.mark.parametrize("history_exchanges", [1, 5, 10, 20, 50])
async def test_full_history_reaches_the_model_without_dropping_or_shortening_turns(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
    history_exchanges: int,
) -> None:
    questions = [
        f"Meal planning question {number}. "
        + "Describe how you compare delivery options before choosing dinner. " * 5
        + f"Question sentinel {number} is at the end."
        for number in range(history_exchanges + 1)
    ]
    replies = [
        f"I plan dinner for exchange {number}. "
        + "I compare delivery options carefully and keep my own meal preferences. " * 5
        + f"Reply sentinel {number} is at the end."
        for number in range(history_exchanges + 1)
    ]
    llm, adapter = await _roomy_llm(llm_factory, replies)
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Keep the full meal-planning history", user_id="test-interview-owner")
    async with session_maker() as session:
        stored = await session.get(Conversations, conversation.id)
        assert stored is not None
        stored.max_turns = 2 * (history_exchanges + 1) + 2
        stored.configuration = {**stored.configuration, "max_turns": stored.max_turns}
        await session.commit()

    expected_history: list[tuple[str, str]] = []
    for index, (question, reply) in enumerate(zip(questions, replies, strict=True)):
        result = await engine.ask(conversation.id, question)
        assert result["reply"] == reply
        assert result["is_finished"] is False
        assert result["max_turns"] > 2 * (history_exchanges + 1)
        request = adapter.requests[index]
        assert request.task == TaskType.PERSONA_INTERVIEW
        assert request.persona_id == stored_persona.id
        assert request.conversation_id == conversation.id
        assert request.messages[0].role == "system"
        assert [(message.role, message.content) for message in request.messages[1:]] == [
            *expected_history,
            ("user", question),
        ]
        expected_history.extend([("user", question), ("assistant", reply)])

    assert len(adapter.requests) == history_exchanges + 1
    stored, turns = await engine.transcript(conversation.id)
    assert [turn.turn_number for turn in turns] == list(range(1, len(expected_history) + 1))
    assert [(turn.role, turn.content) for turn in turns] == [
        ("interviewer" if role == "user" else "persona", content)
        for role, content in expected_history
    ]
    assert stored.turn_count == len(expected_history)
    assert stored.question_count == history_exchanges + 1
    assert stored.status == "active"


async def test_identity_prompt_preserves_every_item_in_lists_longer_than_four(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
) -> None:
    identity_lists = {
        field: [f"{field} item {number} must remain intact through its sentinel tail."
                for number in range(6)]
        for field in ("goals", "pain_points", "objections", "behaviors")
    }
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        assert persona is not None
        for field, values in identity_lists.items():
            setattr(persona, field, values)
        persona.version += 1
        await session.commit()

    llm, adapter = await _roomy_llm(llm_factory, ["I compare meal options.", "I plan ahead."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Explore the complete identity", user_id="test-interview-owner")
    await engine.ask(conversation.id, "How do you choose dinner?")
    await engine.ask(conversation.id, "What else matters to you?")

    assert len(adapter.requests) == 2
    for request in adapter.requests:
        system = request.messages[0].content
        missing = [
            value
            for values in identity_lists.values()
            for value in values
            if value not in system
        ]
        assert missing == [], f"Identity items missing from the model request: {missing}"


async def test_evidence_prompt_preserves_every_citation_and_full_claim(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
) -> None:
    citations = [
        {
            "claim": (
                f"Synthetic evidence claim {number} begins here. "
                + "The complete observation includes meal preferences and delivery constraints. " * 5
                + f"Evidence claim sentinel {number} must remain at the end."
            ),
            "source": f"synthetic-fixture-source-{number}",
        }
        for number in range(6)
    ]
    assert all(len(citation["claim"]) > 180 for citation in citations)
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        assert persona is not None
        persona.evidence_citations = citations
        persona.version += 1
        await session.commit()

    llm, adapter = await _roomy_llm(llm_factory, ["I compare delivery options."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Retain all supplied evidence", user_id="test-interview-owner")
    await engine.ask(conversation.id, "What matters when ordering dinner?")

    assert len(adapter.requests) == 1
    system = adapter.requests[0].messages[0].content
    missing = [
        value
        for citation in citations
        for value in (citation["source"], citation["claim"])
        if value not in system
    ]
    assert missing == [], f"Evidence missing or shortened in the model request: {missing}"


async def test_second_memory_failure_rolls_back_turns_counters_and_first_memory(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = "I compare meal prices and choose affordable delivery."
    llm, adapter = await _roomy_llm(llm_factory, [reply])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Atomic meal-budget interview", user_id="test-interview-owner")
    before = await _persisted_state(session_maker, conversation)
    assert before["turns"] == before["memories"] == []
    assert (before["conversation"]["turn_count"], before["conversation"]["question_count"]) == (0, 0)
    original_remember = memory_service.remember
    remembered: list[MemoryRecord] = []
    memory_attempts = 0

    async def fail_second_memory(*args: Any, **kwargs: Any) -> MemoryRecord:
        nonlocal memory_attempts
        memory_attempts += 1
        if memory_attempts == 2:
            raise RuntimeError("injected failure on second memory write")
        record = await original_remember(*args, **kwargs)
        remembered.append(record)
        return record

    monkeypatch.setattr(memory_service, "remember", fail_second_memory)
    with pytest.raises(RuntimeError, match="injected failure on second memory write"):
        await engine.ask(conversation.id, "What price would fit your meal budget?")

    assert memory_attempts == 2
    assert len(remembered) == 1
    assert remembered[0].text == reply
    assert remembered[0].source == "persona"
    assert remembered[0].conversation_id == conversation.id
    assert len(adapter.requests) == 1
    after = await _persisted_state(session_maker, conversation)
    assert (after["turns"], after["conversation"]["turn_count"],
            after["conversation"]["question_count"], after["memories"]) == ([], 0, 0, [])
    assert after == before


async def test_changed_persona_version_fails_before_llm_or_interview_writes(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
) -> None:
    llm, adapter = await _roomy_llm(llm_factory, ["This reply must never be requested."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Keep the starting persona version", user_id="test-interview-owner")
    before = await _persisted_state(session_maker, conversation)
    assert before["turns"] == before["memories"] == []
    assert (before["conversation"]["turn_count"], before["conversation"]["question_count"]) == (0, 0)
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        assert persona is not None
        assert persona.version == conversation.persona_version
        persona.version = conversation.persona_version + 1
        await session.commit()

    with pytest.raises(Exception, match=r"(?i)(persona.*(?:version|changed)|version.*persona)") as failure:
        await engine.ask(conversation.id, "How do you choose your meals?")

    assert not isinstance(failure.value, (AttributeError, TypeError))
    assert adapter.calls == []
    assert adapter.requests == []
    assert await _persisted_state(session_maker, conversation) == before
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        assert persona is not None
        assert persona.version == conversation.persona_version + 1


class _ContentionObservedLock(asyncio.Lock):
    def __init__(self, contended: asyncio.Event) -> None:
        super().__init__()
        self._contended = contended

    async def acquire(self) -> bool:
        if self.locked():
            self._contended.set()
        return await super().acquire()


async def test_complete_waits_for_in_flight_ask_and_synthesizes_its_committed_turns(
    session_maker: sessionmaker[AsyncSession],
    stored_persona: PersonaProfile,
    memory_service: MemoryService,
    llm_factory: LLMFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = "How do you choose dinner?"
    reply = "I compare meal prices before ordering dinner."
    summary = "The participant compares meal prices before ordering dinner."
    llm, adapter = await _roomy_llm(
        llm_factory,
        [reply, json.dumps({"summary": summary, "key_findings": [summary], "insights": []})],
    )
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Complete only after the current exchange", user_id="test-interview-owner")
    model_entered = asyncio.Event()
    release_reply = asyncio.Event()
    completion_waiting = asyncio.Event()
    monkeypatch.setitem(
        engine._turn_locks, conversation.id, _ContentionObservedLock(completion_waiting)
    )
    original_complete = adapter.complete

    async def gated_complete(candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        if request.task == TaskType.PERSONA_INTERVIEW:
            model_entered.set()
            await release_reply.wait()
        return await original_complete(candidate, request)

    monkeypatch.setattr(adapter, "complete", gated_complete)
    ask_task = asyncio.create_task(engine.ask(conversation.id, question))
    tasks: list[asyncio.Task[Any]] = [ask_task]
    try:
        await asyncio.wait_for(model_entered.wait(), timeout=10)
        complete_task = asyncio.create_task(engine.complete(conversation.id))
        lock_waiter = asyncio.create_task(completion_waiting.wait())
        tasks.extend([complete_task, lock_waiter])
        finished, _ = await asyncio.wait(
            [complete_task, lock_waiter], timeout=10, return_when=asyncio.FIRST_COMPLETED
        )
        assert finished, "Completion neither waited for the in-flight ask nor returned."
        assert not complete_task.done(), "Completion returned before the in-flight ask committed."
        assert completion_waiting.is_set()
        release_reply.set()
        ask_result, completion = await asyncio.wait_for(
            asyncio.gather(ask_task, complete_task), timeout=10
        )
    finally:
        release_reply.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert ask_result["reply"] == reply
    assert completion["status"] == "completed"
    assert completion["summary"] == summary
    assert [request.task for request in adapter.requests] == [
        TaskType.PERSONA_INTERVIEW, TaskType.STRUCTURED_OUTPUT
    ]
    synthesis_prompt = adapter.requests[-1].messages[-1].content
    assert question in synthesis_prompt
    assert reply in synthesis_prompt
    state = await _persisted_state(session_maker, conversation)
    assert state["conversation"]["status"] == "completed"
    assert (state["conversation"]["turn_count"], state["conversation"]["question_count"]) == (2, 1)
    assert [(turn["role"], turn["content"]) for turn in state["turns"]] == [
        ("interviewer", question), ("persona", reply)
    ]
    assert {(memory["source"], memory["text"]) for memory in state["memories"]} == {
        ("interviewer", question), ("persona", reply)
    }
    with pytest.raises(InterviewFinished):
        await engine.ask(conversation.id, "This question is too late.")
    assert len(adapter.requests) == 2


@pytest.mark.parametrize("changed_field", ["persona", "persona_version", "status", "turn_count", "question_count"])
async def test_in_flight_turn_rejects_changed_snapshot_without_writing(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
    changed_field: str,
) -> None:
    llm, adapter = await _roomy_llm(llm_factory, ["This stale reply must not be stored."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Preserve the starting snapshot", user_id="test-interview-owner")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_complete = llm.complete

    async def gated_complete(request: LLMRequest):
        entered.set()
        await release.wait()
        return await original_complete(request)

    monkeypatch.setattr(llm, "complete", gated_complete)
    task = asyncio.create_task(engine.ask(conversation.id, "How do you plan dinner?"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        async with session_maker() as session:
            if changed_field == "persona":
                await session.execute(
                    update(Personas).where(Personas.id == stored_persona.id)
                    .values(version=Personas.version + 1)
                )
            else:
                changed_value = "completed" if changed_field == "status" else 2
                await session.execute(
                    update(Conversations).where(Conversations.id == conversation.id)
                    .values(**{changed_field: changed_value})
                )
            await session.commit()
        before = await _persisted_state(session_maker, conversation)
        release.set()
        with pytest.raises(ExplicitFailure) as failure:
            await asyncio.wait_for(task, timeout=10)
        assert failure.value.status_code == 409
        assert failure.value.error_code == (
            "persona_version_conflict" if changed_field == "persona" else "interview_conflict"
        )
        assert await _persisted_state(session_maker, conversation) == before
        assert len(adapter.requests) == 1
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("streaming", [False, True])
async def test_different_engines_reject_a_stale_reply_after_another_exchange_commits(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
    streaming: bool,
) -> None:
    stale_llm, _ = await _roomy_llm(llm_factory, ["Stale meal choice."])
    winner_llm, _ = await _roomy_llm(llm_factory, ["I compare meal prices."])
    stale_engine = InterviewEngine(stale_llm, session_maker, memory=memory_service)
    winner_engine = InterviewEngine(winner_llm, session_maker, memory=memory_service)
    conversation = await stale_engine.start(stored_persona.id, "Concurrent meal planning", user_id="test-interview-owner")
    entered = asyncio.Event()
    release = asyncio.Event()

    if streaming:
        original_stream = stale_llm.stream

        async def gated_stream(request: LLMRequest):
            entered.set()
            await release.wait()
            async for event in original_stream(request):
                yield event

        monkeypatch.setattr(stale_llm, "stream", gated_stream)
    else:
        original_complete = stale_llm.complete

        async def gated_complete(request: LLMRequest):
            entered.set()
            await release.wait()
            return await original_complete(request)

        monkeypatch.setattr(stale_llm, "complete", gated_complete)

    async def stale_turn() -> None:
        if streaming:
            async for _event in stale_engine.ask_stream(conversation.id, "Stale question?"):
                pass
        else:
            await stale_engine.ask(conversation.id, "Stale question?")

    task = asyncio.create_task(stale_turn())
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        winner = await winner_engine.ask(conversation.id, "How do you choose meals?")
        before = await _persisted_state(session_maker, conversation)
        release.set()
        with pytest.raises(ExplicitFailure) as failure:
            await asyncio.wait_for(task, timeout=10)
        assert failure.value.error_code == "interview_conflict"
        assert failure.value.status_code == 409
        assert await _persisted_state(session_maker, conversation) == before
        assert winner["turn_count"] == before["conversation"]["turn_count"] == 2
        assert before["conversation"]["question_count"] == 1
        assert len(before["turns"]) == len(before["memories"]) == 2
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("new_engine", [False, True])
async def test_successful_completion_is_idempotent_across_engines(
    session_maker, stored_persona, memory_service, llm_factory,
    empty: bool, new_engine: bool,
) -> None:
    synthesis = json.dumps({
        "summary": "The participant compares meal prices.",
        "key_findings": ["Meal prices matter."],
        "insights": [{
            "type": "pricing", "title": "Meal prices", "description": "Compares prices.",
            "supporting_turn_numbers": [2], "confidence": 0.7,
        }],
    })
    llm, adapter = await _roomy_llm(llm_factory, ["I compare meal prices.", synthesis])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Complete once", user_id="test-interview-owner")
    if not empty:
        await engine.ask(conversation.id, "How do you choose meals?")
    first = await engine.complete(conversation.id)
    before = await _persisted_state(session_maker, conversation)
    consumer = InterviewEngine(llm, session_maker, memory=memory_service) if new_engine else engine
    second = await consumer.complete(conversation.id)
    assert second == first
    assert await _persisted_state(session_maker, conversation) == before
    assert len(adapter.requests) == (0 if empty else 2)
    async with session_maker() as session:
        insights = list((await session.execute(
            select(InterviewInsights).where(InterviewInsights.interview_id == conversation.id)
        )).scalars())
    assert len(insights) == (0 if empty else 1)


async def test_failed_synthesis_can_retry_then_success_is_idempotent(
    session_maker, stored_persona, memory_service, llm_factory,
) -> None:
    llm, adapter = await _roomy_llm(llm_factory, [
        "I compare prices.", "not JSON", "still not JSON",
        json.dumps({"summary": "The participant compares prices.", "insights": []}),
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Recover synthesis", user_id="test-interview-owner")
    await engine.ask(conversation.id, "How do you choose dinner?")
    failed = await engine.complete(conversation.id)
    assert failed["source"] == "unavailable"
    assert failed["summary"] is None
    assert failed["error_code"] == "interview_synthesis_unparseable"
    recovered = await engine.complete(conversation.id)
    assert recovered["source"] == "llm"
    assert recovered["summary"] == "The participant compares prices."
    assert await engine.complete(conversation.id) == recovered
    assert len(adapter.requests) == 4


@pytest.mark.parametrize("during_generation", [False, True])
async def test_completion_rejects_persona_version_changes_without_writes(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
    during_generation: bool,
) -> None:
    llm, adapter = await _roomy_llm(llm_factory, [
        "I compare prices.", json.dumps({"summary": "A stale synthesis.", "insights": []}),
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Preserve synthesis identity", user_id="test-interview-owner")
    await engine.ask(conversation.id, "How do you choose dinner?")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_complete = llm.complete

    async def gated_complete(request: LLMRequest):
        entered.set()
        await release.wait()
        return await original_complete(request)

    if during_generation:
        monkeypatch.setattr(llm, "complete", gated_complete)
        task = asyncio.create_task(engine.complete(conversation.id))
    else:
        task = None
    try:
        if during_generation:
            await asyncio.wait_for(entered.wait(), timeout=10)
        async with session_maker() as session:
            await session.execute(update(Personas).where(Personas.id == stored_persona.id)
                                  .values(version=Personas.version + 1))
            await session.commit()
        before = await _persisted_state(session_maker, conversation)
        release.set()
        with pytest.raises(ExplicitFailure) as failure:
            if task is None:
                await engine.complete(conversation.id)
            else:
                await asyncio.wait_for(task, timeout=10)
        assert failure.value.error_code == "persona_version_conflict"
        assert await _persisted_state(session_maker, conversation) == before
        assert len(adapter.requests) == (2 if during_generation else 1)
    finally:
        release.set()
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("competing_operation", ["ask", "complete"])
async def test_stale_completion_cannot_overwrite_another_engine_commit(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
    competing_operation: str,
) -> None:
    first_llm, _ = await _roomy_llm(llm_factory, [
        "I plan dinner.", json.dumps({"summary": "Stale summary.", "insights": []}),
    ])
    second_reply = "I compare meal prices." if competing_operation == "ask" else json.dumps({
        "summary": "The winning synthesis.", "insights": [],
    })
    second_llm, _ = await _roomy_llm(llm_factory, [second_reply])
    first_engine = InterviewEngine(first_llm, session_maker, memory=memory_service)
    second_engine = InterviewEngine(second_llm, session_maker, memory=memory_service)
    conversation = await first_engine.start(stored_persona.id, "Do not overwrite concurrent work", user_id="test-interview-owner")
    await first_engine.ask(conversation.id, "How do you plan meals?")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_complete = first_llm.complete

    async def gated_complete(request: LLMRequest):
        entered.set()
        await release.wait()
        return await original_complete(request)

    monkeypatch.setattr(first_llm, "complete", gated_complete)
    task = asyncio.create_task(first_engine.complete(conversation.id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        if competing_operation == "ask":
            await second_engine.ask(conversation.id, "What do you compare?")
        else:
            await second_engine.complete(conversation.id)
        before = await _persisted_state(session_maker, conversation)
        release.set()
        with pytest.raises(ExplicitFailure) as failure:
            await asyncio.wait_for(task, timeout=10)
        assert failure.value.error_code == "interview_conflict"
        assert await _persisted_state(session_maker, conversation) == before
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("operation", ["ask", "suggest", "complete"])
async def test_all_interview_prompts_preserve_full_context_outside_transactions(
    async_engine, session_maker, stored_persona, llm_factory, monkeypatch,
    operation: str,
) -> None:
    replies = {
        "ask": "I compare prices.",
        "suggest": json.dumps({"questions": ["What matters most when choosing dinner?"]}),
        "complete": json.dumps({"summary": "Meal planning matters.", "insights": []}),
    }
    llm, adapter = await _roomy_llm(llm_factory, [replies[operation]])
    engine = InterviewEngine(llm, session_maker, suggest_questions=True)
    identity_lists = {
        field: [f"{field} identity value {number} sentinel" for number in range(7)]
        for field in ("goals", "pain_points", "objections", "behaviors")
    }
    citations = [{
        "source": f"Synthetic fixture source {number}",
        "claim": f"Claim {number} " + "Complete meal planning evidence. " * 20 + f"claim tail {number}",
    } for number in range(7)]
    segment_traits = {f"trait_{number}": f"Segment identity trait {number}" for number in range(6)}
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        for field, values in identity_lists.items():
            setattr(persona, field, values)
        persona.evidence_citations = citations
        persona.segment_id = "segment-full-context"
        persona.version += 1
        session.add(MarketSegments(
            id=persona.segment_id, study_id="study-full-context", name="Meal planners",
            segmentation_run_id="segmentation-full-context", description="Synthetic meal planners",
            population_percentage=100.0, population_count=10, characteristics=segment_traits,
        ))
        await session.commit()
    conversation = await engine.start(stored_persona.id, "Keep every supplied context item", user_id="test-interview-owner")
    history = [
        ConversationTurns(
            id=f"full-context-turn-{number}", conversation_id=conversation.id,
            turn_number=number + 1, role="interviewer" if number % 2 == 0 else "persona",
            content=f"History {number} " + "Complete meal planning history. " * 25 + f"history tail {number}",
        )
        for number in range(8)
    ]
    async with session_maker() as session:
        session.add_all(history)
        stored = await session.get(Conversations, conversation.id)
        stored.turn_count = 8
        stored.question_count = 4
        await session.commit()

    transactions = set()

    def opened(connection) -> None:
        transactions.add(connection)

    def closed(connection) -> None:
        transactions.discard(connection)

    event.listen(async_engine.sync_engine, "begin", opened)
    event.listen(async_engine.sync_engine, "commit", closed)
    event.listen(async_engine.sync_engine, "rollback", closed)
    original_complete = llm.complete

    async def checked_complete(request: LLMRequest):
        assert not transactions, "A database transaction is still open across the LLM call."
        return await original_complete(request)

    monkeypatch.setattr(llm, "complete", checked_complete)
    try:
        if operation == "ask":
            await engine.ask(conversation.id, "How do you choose dinner?")
        elif operation == "suggest":
            await engine.refresh_suggestions(
                conversation.id, owner_id="test-interview-owner", expected_turn_count=8,
                persona_version=conversation.persona_version,
            )
        else:
            await engine.complete(conversation.id)
    finally:
        event.remove(async_engine.sync_engine, "begin", opened)
        event.remove(async_engine.sync_engine, "commit", closed)
        event.remove(async_engine.sync_engine, "rollback", closed)
    assert len(adapter.requests) == 1
    for request in adapter.requests:
        assert request.persona_id == stored_persona.id
        assert request.conversation_id == conversation.id
        prompt = "\n".join(message.content for message in request.messages)
        expected = [
            *(value for values in identity_lists.values() for value in values),
            *(value for citation in citations for value in citation.values()),
            *(turn.content for turn in history),
        ]
        if operation == "ask" and request.task == TaskType.PERSONA_INTERVIEW:
            expected.extend(segment_traits.values())
        assert [value for value in expected if value not in prompt] == []


async def test_both_memories_share_the_finalization_session_and_one_commit(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
) -> None:
    llm, _ = await _roomy_llm(llm_factory, ["I compare meal prices."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "One exchange transaction", user_id="test-interview-owner")
    write_sessions = []
    commits = []
    original_remember = memory_service.remember

    def committed(session) -> None:
        commits.append(session)

    async def observed_remember(*args, **kwargs):
        session = kwargs.get("session")
        assert isinstance(session, AsyncSession)
        assert session.in_transaction()
        if not write_sessions:
            event.listen(session.sync_session, "after_commit", committed)
        write_sessions.append(session)
        return await original_remember(*args, **kwargs)

    monkeypatch.setattr(memory_service, "remember", observed_remember)
    try:
        await engine.ask(conversation.id, "How do you choose meals?")
        assert len(write_sessions) == 2
        assert write_sessions[0] is write_sessions[1]
        assert commits == [write_sessions[0].sync_session]
        state = await _persisted_state(session_maker, conversation)
        assert len(state["turns"]) == len(state["memories"]) == 2
        assert (state["conversation"]["turn_count"], state["conversation"]["question_count"]) == (2, 1)
    finally:
        if write_sessions:
            event.remove(write_sessions[0].sync_session, "after_commit", committed)


async def test_legacy_profile_projection_cannot_hide_canonical_version_change(
    session_maker, stored_persona, memory_service, llm_factory,
) -> None:
    llm, adapter = await _roomy_llm(llm_factory, ["This must not be requested."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Canonical identity version", user_id="test-interview-owner")
    async with session_maker() as session:
        await session.execute(update(Personas).where(Personas.id == stored_persona.id)
                              .values(demographics={}, version=Personas.version + 1))
        await session.commit()
    before = await _persisted_state(session_maker, conversation)
    with pytest.raises(ExplicitFailure) as failure:
        await engine.ask(conversation.id, "What matters to you?")
    assert failure.value.error_code == "persona_version_conflict"
    assert adapter.requests == []
    assert await _persisted_state(session_maker, conversation) == before