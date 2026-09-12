import pytest

from bebshax.auth.models import Users
from bebshax.db.models import Personas, Studies
from bebshax.interview.orm import Conversations
from bebshax.memory.orm import MemoryItems


@pytest.mark.parametrize(
    "persona_owner,conversation_owners,memory_conversation,study_owner,expected",
    [
        ("usr_system_holder", ["owner-first", "owner-second"], "conversation-0", None, "owner-first"),
        ("usr_system_holder", ["owner-first", "owner-second"], None, None, None),
        ("owner-first", ["owner-first"], None, None, "owner-first"),
        ("owner-first", ["owner-first", "owner-second"], None, None, None),
        ("owner-first", [None], None, None, None),
        ("owner-first", ["usr_default"], "conversation-0", None, None),
        ("missing-user", [], None, None, None),
        ("owner-first", [], "missing-conversation", None, None),
        ("usr_system_holder", ["owner-first"], "conversation-0", "owner-second", None),
        ("owner-first", [], None, "owner-second", None),
    ],
)
async def test_legacy_backfill_only_proposes_verifiable_unambiguous_owner(
    session_maker, persona_owner, conversation_owners, memory_conversation, study_owner, expected,
):
    from bebshax.memory.legacy import infer_legacy_memory_owner

    async with session_maker() as session:
        session.add_all([
            Users(id=owner, email=f"{owner}@example.invalid", full_name=owner,
                  is_active=True, is_verified=True)
            for owner in ("owner-first", "owner-second", "usr_system_holder")
        ])
        if study_owner:
            session.add(Studies(id="legacy-study", user_id=study_owner, title="Legacy study"))
        session.add(Personas(
            id="legacy-persona", owner_id=persona_owner, name="Synthetic legacy persona",
            study_id="legacy-study" if study_owner else None,
        ))
        await session.flush()
        for index, owner in enumerate(conversation_owners):
            session.add(Conversations(
                id=f"conversation-{index}", user_id=owner, persona_id="legacy-persona",
                study_id="legacy-study" if study_owner else None, objective="Historical study",
            ))
        await session.commit()
        memory = MemoryItems(
            id="legacy-memory", persona_id="legacy-persona", owner_id=None,
            text="Full synthetic historical text", kind="episodic", source="persona",
            conversation_id=memory_conversation,
        )
        assert await infer_legacy_memory_owner(session, memory) == expected
        assert memory.owner_id is None