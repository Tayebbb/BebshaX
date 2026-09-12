import asyncio

import pytest
from sqlalchemy import func, select

from bebshax.interview.engine import InterviewEngine
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm import LLMResult, LLMService
from bebshax.llm.adapters.base import StreamDelta
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.governance import get_llm_request_context
from bebshax.llm.provenance import ProvenanceRecord
from bebshax.memory.orm import MemoryItems


class BoundaryLLM(LLMService):
    def __init__(self, text="I compare meal prices.", delay=0):
        self.text = text
        self.delay = delay
        self.requests = []
        self.deadlines = []

    async def complete(self, request, *, deadline_at=None):
        self.requests.append(request)
        self.deadlines.append(deadline_at)
        if self.delay:
            await asyncio.sleep(self.delay)
        return LLMResult(
            text=self.text, provider="fake", model="boundary",
            provenance=ProvenanceRecord(
                request_id=request.request_id, task=request.task,
                persona_id=request.persona_id, conversation_id=request.conversation_id,
                success=True, served_by_provider="fake", served_by_model="boundary",
            ),
        )

    async def stream(self, request, *, deadline_at=None):
        yield StreamDelta(text="Provisional text")
        yield await self.complete(request, deadline_at=deadline_at)


@pytest.mark.parametrize("operation", ["blocking", "stream", "synthesis", "suggestions"])
async def test_interview_operations_bind_trusted_private_context(
    session_maker, stored_persona, llm_factory, monkeypatch, operation,
):
    llm, adapter = llm_factory([
        "I compare meal prices.", '{"summary":"Meal prices matter.","insights":[],"questions":["What changed?"]}',
    ])
    contexts = []
    original = adapter.complete

    async def observe(candidate, request):
        contexts.append(get_llm_request_context())
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    async with session_maker() as session:
        session.add(Studies(id="private-context-study", user_id="owner-first", title="Private research"))
        await session.commit()
    engine = InterviewEngine(llm, session_maker, suggest_questions=True)
    conversation = await engine.start(
        stored_persona.id, "Meals", user_id="owner-first", study_id="private-context-study",
    )
    previous_context = get_llm_request_context()
    if operation == "stream":
        events = [event async for event in engine.ask_stream(conversation.id, "How do you compare meals?")]
        assert events[-1]["type"] == "done"
    else:
        await engine.ask(conversation.id, "How do you compare meals?")
        if operation == "synthesis":
            await engine.complete(conversation.id, owner_id="owner-first")
        elif operation == "suggestions":
            await engine.refresh_suggestions(
                conversation.id, owner_id="owner-first", expected_turn_count=2, persona_version=1,
            )
    assert contexts and all(context is not None for context in contexts)
    assert all(context.owner_user_id == "owner-first" for context in contexts)
    assert all(context.study_id == "private-context-study" for context in contexts)
    assert all(context.data_classification == "private" for context in contexts)
    assert all(request.owner_user_id == "owner-first" for request in adapter.requests)
    assert all(request.study_id == "private-context-study" for request in adapter.requests)
    assert get_llm_request_context() is previous_context


@pytest.mark.parametrize("text", ["", "   \n", "{{reply}}"])
async def test_native_stream_rejects_invalid_terminal_without_persisting(
    session_maker, stored_persona, text,
):
    engine = InterviewEngine(BoundaryLLM(text=text), session_maker)
    conversation = await engine.start(stored_persona.id, "Terminal validation", user_id="owner-first")
    events = []

    with pytest.raises(AttemptFailed) as raised:
        async for event in engine.ask_stream(conversation.id, "How do you compare meals?"):
            events.append(event)

    assert raised.value.kind == FailureKind.MALFORMED_RESPONSE
    assert raised.value.provenance is not None
    assert all(event["type"] != "done" for event in events)
    assert (await engine.transcript(conversation.id))[1] == []
    assert engine._turn_locks == {}


@pytest.mark.parametrize("stage", ["assembly", "inference", "persistence"])
async def test_absolute_deadline_includes_every_mandatory_stage(
    session_maker, stored_persona, monkeypatch, stage,
):
    llm = BoundaryLLM(delay=0.2 if stage == "inference" else 0)
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(stored_persona.id, "Deadline", user_id="owner-first")
    if stage != "inference":
        method_name = "_prepare_turn" if stage == "assembly" else "_update_snapshot"
        original = getattr(engine, method_name)

        async def delayed(*args, **kwargs):
            await asyncio.sleep(0.2)
            return await original(*args, **kwargs)

        monkeypatch.setattr(engine, method_name, delayed)
    deadline = asyncio.get_running_loop().time() + 0.05

    with pytest.raises(TimeoutError):
        await engine.ask(conversation.id, "How do you compare meals?", deadline_at=deadline)

    assert (await engine.transcript(conversation.id))[1] == []
    assert engine._turn_locks == {}
    if llm.deadlines:
        assert llm.deadlines == [deadline]


async def test_memory_recall_crosses_only_same_owner_conversations(
    session_maker, stored_persona, memory_service,
):
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    first = await engine.start(stored_persona.id, "First owner's meals", user_id="owner-first")
    other = await engine.start(stored_persona.id, "Second owner's meals", user_id="owner-second")
    next_conversation = await engine.start(
        stored_persona.id, "First owner's next interview", user_id="owner-first"
    )
    await engine.ask(first.id, "How do you compare meal prices?")
    llm.text = "My private meal preference is the second synthetic owner's statement."
    await engine.ask(other.id, "How do you compare meal prices?")
    assert "I compare meal prices." not in llm.requests[-1].messages[0].content
    llm.text = "I still compare meal prices."
    result = await engine.ask(next_conversation.id, "How do you compare meal prices?")

    assert result["retrieved_memories"] == ["I compare meal prices."]
    assert "second synthetic owner's statement" not in llm.requests[-1].messages[0].content
    async with session_maker() as session:
        assert await session.scalar(select(func.count()).select_from(ConversationTurns)) == 6
        rows = list((await session.execute(select(MemoryItems))).scalars())
    assert {row.owner_id for row in rows} == {"owner-first", "owner-second"}


async def test_interview_uses_full_creation_snapshot_without_rewriting_persona(
    session_maker, stored_persona,
):
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(stored_persona.id, "Stable identity", user_id="owner-first")
    async with session_maker() as session:
        persona = await session.get(Personas, stored_persona.id)
        persona.name = "Later mutable persona name"
        persona.demographics = {"age": 70, "location": "Later location"}
        await session.commit()

    await engine.ask(conversation.id, "Who are you?")

    assert stored_persona.name in llm.requests[0].messages[0].content
    assert "Later mutable persona name" not in llm.requests[0].messages[0].content
    async with session_maker() as session:
        saved = await session.get(Conversations, conversation.id)
        live = await session.get(Personas, stored_persona.id)
        assert saved.persona_snapshot["identity_card"]
        assert saved.persona_snapshot["fields"]["name"] == stored_persona.name
        assert live.name == "Later mutable persona name"


@pytest.mark.parametrize("streaming", [False, True])
async def test_interview_includes_complete_stored_study_context(session_maker, stored_persona, streaming):
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    prompt = "Complete synthetic business idea " * 300 + "business-context-tail"
    history = "Prior synthetic copilot context " * 200 + "copilot-context-tail"
    async with session_maker() as session:
        session.add(Studies(
            id="full-study-context", user_id="owner-first", title="Meal research", prompt=prompt,
            copilot_messages=[{"role": "user", "content": history}], findings={"summary": "finding-context-tail"},
        ))
        await session.commit()
    conversation = await engine.start(
        stored_persona.id, "Meal research", user_id="owner-first", study_id="full-study-context",
    )
    if streaming:
        events = [event async for event in engine.ask_stream(conversation.id, "What matters about meals?")]
        assert events[-1]["type"] == "done"
    else:
        await engine.ask(conversation.id, "What matters about meals?")
    context = "\n".join(message.content for message in llm.requests[-1].messages)
    assert prompt in context
    assert history in context
    assert "finding-context-tail" in context


async def test_memory_embedding_finishes_before_any_turn_write_lock(
    session_maker, stored_persona, memory_service, monkeypatch,
):
    engine = InterviewEngine(BoundaryLLM(), session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "No provider under locks", user_id="owner-first")
    original_update = engine._update_snapshot
    original_embed = memory_service._embeddings.embed
    writing = False

    async def observe_update(*args, **kwargs):
        nonlocal writing
        writing = True
        return await original_update(*args, **kwargs)

    async def observe_embed(texts):
        assert not writing, "Embedding provider awaited while turn transaction holds locks"
        return await original_embed(texts)

    monkeypatch.setattr(engine, "_update_snapshot", observe_update)
    monkeypatch.setattr(memory_service._embeddings, "embed", observe_embed)
    result = await engine.ask(conversation.id, "How do you compare meals?")
    assert result["reply"] == "I compare meal prices."
    assert result["llm_request_id"]
    assert result["provenance"]["request_id"] == result["llm_request_id"]


async def test_optional_suggestions_retain_full_private_research_and_memory_context(
    session_maker, stored_persona, memory_service,
):
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker, memory=memory_service, suggest_questions=True)
    prompt = "Complete synthetic meal research " * 300 + "suggestion-study-tail"
    history = "Earlier synthetic meal research " * 200 + "suggestion-history-tail"
    objective = "Understand the complete private meal-planning objective."
    recalled_text = "I compare meal prices using a private weekly meal-planning notebook."
    async with session_maker() as session:
        session.add(Studies(
            id="suggestion-context-study", user_id="owner-first", title="Meal research", prompt=prompt,
            copilot_messages=[{"role": "user", "content": history}],
            findings={"summary": "suggestion-findings-tail"},
        ))
        await session.commit()
    await memory_service.remember(stored_persona.id, recalled_text, owner_id="owner-first")
    await memory_service.remember(
        stored_persona.id, "Second owner's private meal-planning marker.", owner_id="owner-second"
    )
    conversation = await engine.start(
        stored_persona.id, objective, user_id="owner-first", study_id="suggestion-context-study",
    )
    await engine.ask(conversation.id, "How do you compare meal prices?")
    llm.text = '{"questions":["What matters about the weekly notebook?"]}'

    await engine.refresh_suggestions(
        conversation.id, owner_id="owner-first", expected_turn_count=2, persona_version=1,
    )

    context = "\n".join(message.content for message in llm.requests[-1].messages)
    assert objective in context
    assert prompt in context
    assert history in context
    assert "suggestion-findings-tail" in context
    assert recalled_text in context
    assert "Second owner's private meal-planning marker." not in context
    assert llm.requests[-1].owner_user_id == "owner-first"
    assert llm.requests[-1].study_id == "suggestion-context-study"


async def test_missing_topic_state_and_optional_suggestions_do_not_delay_primary(
    session_maker, stored_persona, monkeypatch,
):
    engine = InterviewEngine(BoundaryLLM(), session_maker, suggest_questions=True)
    conversation = await engine.start(stored_persona.id, "Unknown topics", user_id="owner-first")
    async with session_maker() as session:
        saved = await session.get(Conversations, conversation.id)
        saved.topics_explored = None
        await session.commit()

    async def forbidden_suggestions(*args, **kwargs):
        raise AssertionError("Generated suggestions must not run on the acknowledgement path")

    monkeypatch.setattr(engine, "generate_suggested_questions", forbidden_suggestions)
    result = await engine.ask(conversation.id, "What matters to you?")
    assert result["suggested_questions"] == []
    assert isinstance(result["topics_explored"], dict)


@pytest.mark.parametrize("stale", [False, True])
async def test_opt_in_suggestions_are_tracked_and_revision_owned(
    session_maker, stored_persona, monkeypatch, stale,
):
    engine = InterviewEngine(
        BoundaryLLM(), session_maker, suggest_questions=True,
        background_suggestions=True, max_background_suggestions=1,
    )
    conversation = await engine.start(stored_persona.id, "Background suggestions", user_id="owner-first")
    entered, release = asyncio.Event(), asyncio.Event()

    async def suggestions(*args, **kwargs):
        entered.set()
        await release.wait()
        return ["What changed about meal planning?"]

    monkeypatch.setattr(engine, "generate_suggested_questions", suggestions)
    try:
        result = await engine.ask(conversation.id, "What matters about meal planning?")
        assert result["suggested_questions"] == []
        await asyncio.wait_for(entered.wait(), 2)
        assert len(engine._suggestion_tasks) == 1
        if stale:
            await engine.ask(conversation.id, "What else matters?")
        tasks = tuple(engine._suggestion_tasks)
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 2)
        _, turns = await engine.transcript(conversation.id)
        assert turns[1].metadata_json["suggested_questions"] == (
            [] if stale else ["What changed about meal planning?"]
        )
    finally:
        release.set()
        await engine.aclose()
    assert engine._suggestion_tasks == set()


async def test_engine_shutdown_cancels_owned_suggestion_tasks(
    session_maker, stored_persona, monkeypatch,
):
    engine = InterviewEngine(BoundaryLLM(), session_maker, suggest_questions=True, background_suggestions=True)
    conversation = await engine.start(stored_persona.id, "Shutdown", user_id="owner-first")
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def suggestions(*args, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(engine, "generate_suggested_questions", suggestions)
    await engine.ask(conversation.id, "How do you plan meals?")
    await asyncio.wait_for(entered.wait(), 2)
    await engine.aclose()
    assert cancelled.is_set()
    assert engine._suggestion_tasks == set()


async def test_synthesis_uses_same_deadline_and_never_commits_late(
    session_maker, stored_persona,
):
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(stored_persona.id, "Bounded synthesis", user_id="owner-first")
    await engine.ask(conversation.id, "How do you compare meals?")
    llm.delay = 0.2
    deadline = asyncio.get_running_loop().time() + 0.05
    with pytest.raises(TimeoutError):
        await engine.complete(conversation.id, owner_id="owner-first", deadline_at=deadline)
    saved, turns = await engine.transcript(conversation.id)
    assert saved.status == "active"
    assert len(turns) == 2
    assert engine._turn_locks == {}


async def test_wrong_owner_cannot_read_or_complete_engine_transcript(
    session_maker, stored_persona,
):
    from bebshax.interview.engine import ConversationNotFound

    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(stored_persona.id, "Private synthesis", user_id="owner-first")
    with pytest.raises(ConversationNotFound):
        await engine.transcript(conversation.id, owner_id="owner-second")
    with pytest.raises(ConversationNotFound):
        await engine.complete(conversation.id, owner_id="owner-second")
    assert llm.requests == []


async def test_post_output_persistence_timeout_carries_terminal_provenance(
    session_maker, stored_persona, monkeypatch,
):
    engine = InterviewEngine(BoundaryLLM(), session_maker)
    conversation = await engine.start(stored_persona.id, "Stream persistence timeout", user_id="owner-first")
    original = engine._update_snapshot

    async def blocked(*args, **kwargs):
        await asyncio.sleep(0.2)
        return await original(*args, **kwargs)

    monkeypatch.setattr(engine, "_update_snapshot", blocked)
    with pytest.raises(AttemptFailed) as raised:
        async for event in engine.ask_stream(
            conversation.id, "How do you plan meals?", deadline_at=asyncio.get_running_loop().time() + 0.06,
        ):
            assert event["type"] == "delta"
    assert raised.value.kind == FailureKind.TIMEOUT
    assert raised.value.provenance.request_id
    assert not raised.value.provenance.success
    assert (await engine.transcript(conversation.id))[1] == []


async def test_snapshot_keeps_full_legacy_evidence_and_synthesizes_it(
    session_maker, stored_persona,
):
    from bebshax.persona.schema import EvidenceItem
    from bebshax.persona.store import save_persona

    evidence_text = "Synthetic full evidence " * 40 + "immutable-evidence-tail"
    profile = stored_persona.model_copy(update={
        "version": 2,
        "evidence": [EvidenceItem(id="full-evidence", source="synthetic-fixture", text=evidence_text)],
    })
    async with session_maker() as session:
        await save_persona(session, profile, owner_id="usr_system_holder")
    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(profile.id, "Full evidence", user_id="owner-first")
    await engine.ask(conversation.id, "What matters about meals?")
    assert evidence_text in "\n".join(message.content for message in llm.requests[-1].messages)
    llm.text = '{"summary":"Meals matter.","insights":[]}'
    await engine.complete(conversation.id)
    assert evidence_text in "\n".join(message.content for message in llm.requests[-1].messages)
    async with session_maker() as session:
        saved = await session.get(Conversations, conversation.id)
        assert saved.persona_snapshot["legacy_profile"]["evidence"][0]["text"] == evidence_text


async def test_profile_kind_snapshot_supports_synthesis(session_maker, stored_persona):
    from bebshax.interview.engine import _capture_persona_snapshot

    llm = BoundaryLLM()
    engine = InterviewEngine(llm, session_maker)
    conversation = await engine.start(stored_persona.id, "Legacy profile", user_id="owner-first")
    async with session_maker() as session:
        saved = await session.get(Conversations, conversation.id)
        saved.persona_snapshot = _capture_persona_snapshot(stored_persona)
        assert saved.persona_snapshot["kind"] == "profile"
        assert saved.persona_snapshot["fields"]["name"] == stored_persona.name
        await session.commit()
    await engine.ask(conversation.id, "What matters about meals?")
    llm.text = '{"summary":"Meals matter.","insights":[]}'
    assert (await engine.complete(conversation.id))["summary"] == "Meals matter."


async def test_cancelled_lock_waiter_does_not_strand_next_turn(session_maker):
    engine = InterviewEngine(BoundaryLLM(), session_maker)
    entered = asyncio.Event()
    release = asyncio.Event()
    completed = []

    async def holder():
        async with engine._conversation_lock("lock-regression"):
            entered.set()
            await release.wait()

    async def waiter(label):
        async with engine._conversation_lock(
            "lock-regression", deadline_at=asyncio.get_running_loop().time() + 2,
        ):
            completed.append(label)

    holding = asyncio.create_task(holder())
    await entered.wait()
    cancelled = asyncio.create_task(waiter("cancelled"))
    successor = asyncio.create_task(waiter("successor"))
    await asyncio.sleep(0)
    release.set()
    cancelled.cancel()
    try:
        await asyncio.wait_for(asyncio.gather(holding, cancelled, successor, return_exceptions=True), 3)
        assert completed == ["successor"]
        assert engine._turn_locks == {}
        assert engine._lock_users == {}
    finally:
        for task in (holding, cancelled, successor):
            if not task.done():
                task.cancel()
        await asyncio.gather(holding, cancelled, successor, return_exceptions=True)