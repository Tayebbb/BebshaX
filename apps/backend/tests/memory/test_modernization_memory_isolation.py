import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import Base
from bebshax.interview.orm import Conversations
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.memory.orm import MemoryItems
from bebshax.memory.service import MemoryService


@pytest.mark.parametrize("operation", ["remember", "retrieve", "list_for_persona", "reflect"])
async def test_memory_requires_an_explicit_owner(session_maker, embeddings, operation):
    service = MemoryService(session_maker, embeddings)
    arguments = ("shared-persona", "Synthetic private observation") if operation in {
        "remember", "retrieve"
    } else ("shared-persona",)

    with pytest.raises(ValueError, match="owner"):
        await getattr(service, operation)(*arguments)


async def test_same_persona_memories_and_dedupe_are_private_to_owner(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    first = await service.remember(
        "shared-persona", "I compare meal prices.", owner_id="owner-first"
    )
    second = await service.remember(
        "shared-persona", "I compare meal prices.", owner_id="owner-second"
    )
    repeat = await service.remember(
        "shared-persona", "I compare meal prices.", owner_id="owner-first"
    )
    private = await service.remember(
        "shared-persona", "Private meal observation for second owner.", owner_id="owner-second"
    )

    assert first.id != second.id
    assert repeat.id == first.id
    retrieved = await service.retrieve(
        "shared-persona", "meal", owner_id="owner-first", min_relevance=0, sources=None
    )
    listed = await service.list_for_persona(
        "shared-persona", owner_id="owner-first", sources=None
    )
    assert [record.id for record in retrieved] == [first.id]
    assert [record.id for record in listed] == [first.id]
    assert private.id not in {record.id for record in retrieved}


async def test_unattributed_legacy_memory_is_not_shared(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    [vector] = await embeddings.embed(["Unattributed synthetic private memory"])
    async with session_maker() as session:
        session.add(MemoryItems(
            id="legacy-unknown", persona_id="shared-persona", kind="episodic",
            text="Unattributed synthetic private memory", embedding=vector,
            embedding_space=embeddings.space, source="persona", importance=0.5,
        ))
        await session.commit()

    assert await service.list_for_persona("shared-persona", owner_id="owner-first") == []
    assert await service.retrieve(
        "shared-persona", "private memory", owner_id="owner-first", min_relevance=0
    ) == []


async def test_owner_can_be_derived_only_from_a_matching_owned_conversation(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    async with session_maker() as session:
        session.add(Conversations(
            id="owned-conversation", persona_id="shared-persona", user_id="owner-first",
            objective="Synthetic meals",
        ))
        await session.commit()
    record = await service.remember(
        "shared-persona", "Private synthetic meal notes", conversation_id="owned-conversation"
    )
    assert record.owner_id == "owner-first"
    assert [item.id for item in await service.retrieve(
        "shared-persona", "meal", conversation_id="owned-conversation", min_relevance=0
    )] == [record.id]
    with pytest.raises(ValueError, match="owner|conversation"):
        await service.remember(
            "shared-persona", "Do not insert this", owner_id="owner-second",
            conversation_id="owned-conversation",
        )
    with pytest.raises(ValueError, match="persona|conversation"):
        await service.remember(
            "different-persona", "Do not insert this", conversation_id="owned-conversation"
        )


@pytest.mark.parametrize("text", ["", " \n ", "[your answer here]", "{{reply}}"])
async def test_invalid_memory_text_is_rejected_not_silently_dropped(session_maker, embeddings, text):
    service = MemoryService(session_maker, embeddings)
    with pytest.raises(ValueError, match="text|placeholder"):
        await service.remember("shared-persona", text, owner_id="owner-first")
    async with session_maker() as session:
        assert list((await session.execute(select(MemoryItems))).scalars()) == []


async def test_empty_source_filter_does_not_disable_source_isolation(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    await service.remember("shared-persona", "Synthetic meal memory", owner_id="owner-first")
    assert await service.retrieve(
        "shared-persona", "meal", owner_id="owner-first", sources=(), min_relevance=0
    ) == []
    assert await service.list_for_persona("shared-persona", owner_id="owner-first", sources=()) == []


async def test_caller_rollback_keeps_even_first_memory_insert_uncommitted(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    async with session_maker() as session:
        await service.remember("shared-persona", "Caller-owned text", owner_id="owner-first", session=session)
        await session.rollback()
    assert await service.list_for_persona("shared-persona", owner_id="owner-first") == []


async def test_database_enforces_private_dedupe_key(session_maker, embeddings):
    service = MemoryService(session_maker, embeddings)
    record = await service.remember("shared-persona", "Canonical synthetic text", owner_id="owner-first")
    async with session_maker() as session:
        original = await session.get(MemoryItems, record.id)
        duplicate = MemoryItems(**{
            column.key: getattr(original, column.key)
            for column in MemoryItems.__table__.columns
        })
        duplicate.id = "duplicate-memory"
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_independent_writers_dedupe_per_owner(tmp_path, embeddings):
    database = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'memory-race.db'}")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = sessionmaker(database, class_=AsyncSession, expire_on_commit=False)
    first = MemoryService(maker, embeddings)
    second = MemoryService(maker, embeddings)
    try:
        rows = await asyncio.gather(
            first.remember("shared-persona", "Full synthetic duplicate text", owner_id="owner-first"),
            second.remember("shared-persona", "Full synthetic duplicate text", owner_id="owner-first"),
            second.remember("shared-persona", "Full synthetic duplicate text", owner_id="owner-second"),
        )
        assert rows[0].id == rows[1].id
        assert rows[0].id != rows[2].id
    finally:
        await database.dispose()


@pytest.mark.parametrize("conversation_id", [None, "reflection-conversation"])
async def test_reflection_inputs_and_outputs_stay_inside_owner(session_maker, embeddings, monkeypatch, conversation_id):
    from bebshax.llm.governance import get_llm_request_context

    adapter = FakeAdapter([FakeRoute(candidate=RouteCandidate(provider="fake", model="reflection"),
        reply='{"insights":["I compare the complete first owner observations."]}')])
    contexts = []
    original = adapter.complete

    async def observe(candidate, request):
        contexts.append(get_llm_request_context())
        return await original(candidate, request)

    monkeypatch.setattr(adapter, "complete", observe)
    service = MemoryService(session_maker, embeddings, llm=SingleAdapterLLMService(adapter))
    if conversation_id is not None:
        async with session_maker() as session:
            session.add(Conversations(
                id=conversation_id, persona_id="shared-persona", user_id="owner-first",
                study_id="reflection-study", objective="Private synthetic reflection",
            ))
            await session.commit()
    for owner in ("owner-first", "owner-second"):
        for index in range(8):
            await service.remember("shared-persona", f"Full {owner} observation {index}", owner_id=owner)
    result = await service.reflect("shared-persona", owner_id="owner-first", conversation_id=conversation_id)
    prompt = adapter.requests[0].messages[-1].content
    assert "owner-first" in prompt
    assert "owner-second" not in prompt
    assert adapter.requests[0].owner_user_id == "owner-first"
    assert contexts[0].owner_user_id == "owner-first"
    assert contexts[0].data_classification == "private"
    expected_study = "reflection-study" if conversation_id is not None else None
    assert adapter.requests[0].study_id == expected_study
    assert contexts[0].study_id == expected_study
    assert result and all(record.owner_id == "owner-first" for record in result)
    assert await service.list_for_persona("shared-persona", kind="reflection", owner_id="owner-second") == []


async def test_reflection_rejects_invalid_later_insight_without_partial_writes(session_maker, embeddings):
    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="fake", model="reflection"),
        reply='{"insights":["I compare complete synthetic observations.","{{reply}}"]}',
    )])
    service = MemoryService(session_maker, embeddings, llm=SingleAdapterLLMService(adapter))
    for index in range(8):
        await service.remember(
            "shared-persona", f"Complete synthetic observation {index}", owner_id="owner-first"
        )

    with pytest.raises(ValueError, match="placeholder"):
        await service.reflect("shared-persona", owner_id="owner-first")

    assert await service.list_for_persona(
        "shared-persona", kind="reflection", owner_id="owner-first"
    ) == []