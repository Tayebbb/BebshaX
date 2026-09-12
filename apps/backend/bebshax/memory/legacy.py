"""Read-only attribution proposals for the coordinator's offline memory migration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.db.models import Businesses, Personas, Studies
from bebshax.interview.orm import Conversations
from bebshax.memory.orm import MemoryItems
from bebshax.personas.orm import PersonaVersions
from bebshax.tenancy import PUBLIC_OWNER_IDS


def _private_owner(owner_id: str | None) -> bool:
    return bool(owner_id and owner_id.strip() and owner_id not in PUBLIC_OWNER_IDS)


async def _parents_match(
    session: AsyncSession, persona: Personas, owner_id: str,
    conversation: Conversations | None = None,
) -> bool:
    if _private_owner(persona.owner_id) and persona.owner_id != owner_id:
        return False
    if _private_owner(persona.user_id) and persona.user_id != owner_id:
        return False
    if (conversation is not None and persona.study_id and conversation.study_id
            and persona.study_id != conversation.study_id):
        return False
    study_ids = {persona.study_id, conversation.study_id if conversation else None} - {None, ""}
    for study_id in study_ids:
        study = await session.get(Studies, study_id)
        if study is None or study.user_id != owner_id:
            return False
    if persona.business_id:
        business = await session.get(Businesses, persona.business_id)
        if business is None or (_private_owner(business.owner_id) and business.owner_id != owner_id):
            return False
    return True


async def infer_legacy_memory_owner(session: AsyncSession, memory: MemoryItems) -> str | None:
    """Return demonstrable ownership or None; never mutate, flush, or guess a tenant."""
    with session.no_autoflush:
        persona = await session.get(Personas, memory.persona_id)
        if persona is None:
            return None
        if memory.conversation_id:
            conversation = await session.get(Conversations, memory.conversation_id)
            if conversation is None or conversation.persona_id != memory.persona_id:
                return None
            owner_id = conversation.user_id
            if (not _private_owner(owner_id) or await session.scalar(select(Users.id).where(Users.id == owner_id)) is None
                    or not await _parents_match(session, persona, owner_id, conversation)):
                return None
            if memory.owner_id is not None and memory.owner_id != owner_id:
                return None
            return owner_id

        owner_id = persona.owner_id
        if (not _private_owner(owner_id) or await session.scalar(select(Users.id).where(Users.id == owner_id)) is None
                or not await _parents_match(session, persona, owner_id)):
            return None
        if memory.owner_id is not None and memory.owner_id != owner_id:
            return None
        version_owners = (await session.scalars(select(PersonaVersions.owner_id).where(
            PersonaVersions.persona_id == persona.id,
        ).distinct())).all()
        if any(version_owner != owner_id for version_owner in version_owners):
            return None
        conversations = (await session.scalars(select(Conversations).where(
            Conversations.persona_id == persona.id,
        ))).all()
        for conversation in conversations:
            if conversation.user_id != owner_id or not await _parents_match(session, persona, owner_id, conversation):
                return None
        other_owners = (await session.scalars(select(MemoryItems.owner_id).where(
            MemoryItems.persona_id == persona.id, MemoryItems.owner_id.is_not(None),
        ).distinct())).all()
        return None if any(other_owner != owner_id for other_owner in other_owners) else owner_id