"""Offline cancellation, stream closure, and conversation-lock lifecycle tests."""

import asyncio
import json

import pytest
from sqlalchemy import func, select

from bebshax.interview.engine import InterviewEngine, InterviewFinished
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm import TaskType
from bebshax.llm.adapters.base import RouteCandidate, StreamDelta, StreamDone
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.router import PoolRouter
from bebshax.memory.orm import MemoryItems


async def _counts(session_maker, conversation) -> tuple[int, int, int, int]:
    async with session_maker() as session:
        stored = await session.get(Conversations, conversation.id)
        turns = await session.scalar(select(func.count()).select_from(ConversationTurns).where(
            ConversationTurns.conversation_id == conversation.id
        ))
        memories = await session.scalar(select(func.count()).select_from(MemoryItems).where(
            MemoryItems.persona_id == conversation.persona_id
        ))
        return stored.turn_count, stored.question_count, turns, memories


@pytest.mark.parametrize("abandonment", ["close", "cancel"])
async def test_abandoned_stream_closes_router_and_releases_conversation_lock(
    session_maker, stored_persona, memory_service, monkeypatch, abandonment: str,
) -> None:
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="stream-test"),
        reply="I compare meal prices.",
    )])
    records = []
    router = PoolRouter(
        {name: adapter for name in ("openrouter", "freellmpool", "ollama")},
        on_provenance=records.append,
    )
    engine = InterviewEngine(router, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Stream cleanup")
    closed = asyncio.Event()
    suspended = asyncio.Event()
    release = asyncio.Event()

    async def controlled_stream(candidate, request):
        try:
            yield StreamDelta(text="Incomplete raw text")
            suspended.set()
            await release.wait()
            yield StreamDone(completion=await adapter.complete(candidate, request))
        finally:
            closed.set()

    monkeypatch.setattr(adapter, "stream", controlled_stream)
    stream = engine.ask_stream(conversation.id, "How do you choose dinner?")
    pending = None
    try:
        assert (await anext(stream))["type"] == "delta"
        if abandonment == "cancel":
            pending = asyncio.create_task(anext(stream))
            await asyncio.wait_for(suspended.wait(), timeout=10)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        await stream.aclose()
        assert closed.is_set()
        assert router.pool_utilization()["conversation"]["active_requests"] == 0
        assert len(records) == 1
        assert records[0].success is False
        assert await _counts(session_maker, conversation) == (0, 0, 0, 0)
        recovered = await asyncio.wait_for(
            engine.ask(conversation.id, "What do you compare?"), timeout=10
        )
        assert recovered["reply"] == "I compare meal prices."
        assert await _counts(session_maker, conversation) == (2, 1, 2, 2)
        assert engine._turn_locks == {}
    finally:
        release.set()
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()


@pytest.mark.parametrize("operation", ["ask", "complete"])
async def test_cancellation_during_llm_releases_lock_without_new_turns(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
    operation: str,
) -> None:
    llm, _ = llm_factory(["I compare prices."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Cancellation")
    if operation == "complete":
        await engine.ask(conversation.id, "What do you compare?")
    before = await _counts(session_maker, conversation)
    entered = asyncio.Event()
    release = asyncio.Event()
    original_complete = llm.complete

    async def blocked_complete(request):
        entered.set()
        await release.wait()
        return await original_complete(request)

    monkeypatch.setattr(llm, "complete", blocked_complete)
    task = asyncio.create_task(
        engine.complete(conversation.id) if operation == "complete"
        else engine.ask(conversation.id, "How do you plan meals?")
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await _counts(session_maker, conversation) == before
        async with session_maker() as session:
            stored = await session.get(Conversations, conversation.id)
            assert stored.status == "active"
            assert stored.summary is None
        assert engine._turn_locks == {}
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancellation_during_second_memory_rolls_back_whole_exchange(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
) -> None:
    llm, _ = llm_factory(["I compare prices."])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Atomic cancellation")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_remember = memory_service.remember
    attempts = 0

    async def blocked_remember(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            entered.set()
            await release.wait()
        return await original_remember(*args, **kwargs)

    monkeypatch.setattr(memory_service, "remember", blocked_remember)
    task = asyncio.create_task(engine.ask(conversation.id, "What do you compare?"))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert attempts == 2
        assert await _counts(session_maker, conversation) == (0, 0, 0, 0)
        assert engine._turn_locks == {}
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class _ObservedLock(asyncio.Lock):
    def __init__(self, queued: list[asyncio.Event]) -> None:
        super().__init__()
        self.queued = queued
        self.contentions = 0

    async def acquire(self) -> bool:
        if self.locked():
            self.queued[self.contentions].set()
            self.contentions += 1
        return await super().acquire()


async def test_lock_stays_shared_until_active_and_queued_operations_finish(
    session_maker, stored_persona, memory_service, llm_factory, monkeypatch,
) -> None:
    llm, adapter = llm_factory([
        "I compare prices.", json.dumps({"summary": "Prices matter.", "insights": []}),
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    conversation = await engine.start(stored_persona.id, "Waiter lifecycle")
    ask_entered, completion_entered = asyncio.Event(), asyncio.Event()
    release_ask, release_completion = asyncio.Event(), asyncio.Event()
    queued = [asyncio.Event() for _index in range(3)]
    lock = _ObservedLock(queued)
    monkeypatch.setitem(engine._turn_locks, conversation.id, lock)
    original_complete = llm.complete

    async def gated_complete(request):
        if request.task == TaskType.PERSONA_INTERVIEW:
            ask_entered.set()
            await release_ask.wait()
        else:
            completion_entered.set()
            await release_completion.wait()
        return await original_complete(request)

    monkeypatch.setattr(llm, "complete", gated_complete)
    first = asyncio.create_task(engine.ask(conversation.id, "What matters?"))
    tasks = [first]
    try:
        await asyncio.wait_for(ask_entered.wait(), timeout=10)
        completion = asyncio.create_task(engine.complete(conversation.id))
        tasks.append(completion)
        await asyncio.wait_for(queued[0].wait(), timeout=10)
        cancelled_waiter = asyncio.create_task(engine.ask(conversation.id, "Queued question?"))
        tasks.append(cancelled_waiter)
        await asyncio.wait_for(queued[1].wait(), timeout=10)
        release_ask.set()
        await asyncio.wait_for(first, timeout=10)
        await asyncio.wait_for(completion_entered.wait(), timeout=10)
        assert engine._turn_locks[conversation.id] is lock
        cancelled_waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_waiter
        assert engine._turn_locks[conversation.id] is lock
        late = asyncio.create_task(engine.ask(conversation.id, "Arrived during completion?"))
        tasks.append(late)
        await asyncio.wait_for(queued[2].wait(), timeout=10)
        release_completion.set()
        assert (await asyncio.wait_for(completion, timeout=10))["status"] == "completed"
        with pytest.raises(InterviewFinished):
            await asyncio.wait_for(late, timeout=10)
        assert [request.task for request in adapter.requests] == [
            TaskType.PERSONA_INTERVIEW, TaskType.STRUCTURED_OUTPUT,
        ]
        assert engine._turn_locks == {}
    finally:
        release_ask.set()
        release_completion.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)