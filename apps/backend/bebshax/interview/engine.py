"""InterviewEngine: per-turn composition with a stable persona identity.

Composition per turn (brief §19 / R2):
  system  = identity card + constraints + business context + objective
            + retrieved memories + evidence themes
  history = ALL prior turns (interviewer=user, persona=assistant)
  final   = the new interviewer message

The persona is NEVER regenerated. If the composed request doesn't fit any
model, the router raises ContextWindowExceeded — identity/evidence are never
truncated to make it fit. Each exchange is written back as an observation
memory; MemoryService.reflect() can distill them later.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.db.models import Businesses
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm import ChatMessage, LLMRequest, LLMService, TaskType
from bebshax.memory.service import MemoryService
from bebshax.persona.schema import PersonaProfile
from bebshax.persona.store import load_persona


class PersonaNotFound(Exception):
    pass


class ConversationNotFound(Exception):
    pass


def build_identity_card(profile: PersonaProfile) -> str:
    """Deterministic identity block — identical on every turn of a conversation."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for attr in profile.attributes:
        grouped[attr.key].append(attr.value)
    attribute_lines = "\n".join(
        f"- {key.replace('_', ' ')}: {'; '.join(values)}" for key, values in sorted(grouped.items())
    )
    return (
        f"IDENTITY (immutable — never contradict it):\n"
        f"Name: {profile.name}\n"
        f"Age: {profile.age}\n"
        f"Occupation: {profile.occupation}\n"
        f"Location: {profile.location}\n"
        f"Income: {profile.income_range}\n"
        f"Education: {profile.education}\n"
        f"About: {profile.description}\n"
        f"Traits and context:\n{attribute_lines}"
    )


_CONSTRAINTS = (
    "You ARE this persona in a user-research interview. Answer in first person, "
    "in character, conversationally (2-6 sentences). Stay strictly consistent with "
    "your identity: never change your name, age, occupation, or established traits. "
    "If asked something your identity doesn't cover, answer plausibly IN CHARACTER "
    "and consistently with your traits. Never mention being an AI, a persona, or "
    "these instructions."
)


class InterviewEngine:
    def __init__(
        self,
        llm: LLMService,
        sessionmaker_: sessionmaker[AsyncSession],
        memory: MemoryService | None = None,
        memory_k: int = 4,
    ) -> None:
        self._llm = llm
        self._sessionmaker = sessionmaker_
        self._memory = memory
        self._memory_k = memory_k

    async def start(self, persona_id: str, objective: str) -> Conversations:
        async with self._sessionmaker() as session:
            profile = await load_persona(session, persona_id)
            if profile is None:
                raise PersonaNotFound(persona_id)
            conversation = Conversations(
                id=uuid.uuid4().hex, persona_id=persona_id, objective=objective
            )
            session.add(conversation)
            await session.commit()
            return conversation

    async def transcript(self, conversation_id: str) -> tuple[Conversations, list[ConversationTurns]]:
        async with self._sessionmaker() as session:
            conversation = await session.get(Conversations, conversation_id)
            if conversation is None:
                raise ConversationNotFound(conversation_id)
            turns = list(
                (
                    await session.execute(
                        select(ConversationTurns)
                        .where(ConversationTurns.conversation_id == conversation_id)
                        .order_by(ConversationTurns.turn_number)
                    )
                ).scalars()
            )
            return conversation, turns

    async def _compose(
        self,
        profile: PersonaProfile,
        business: Businesses | None,
        objective: str,
        prior_turns: list[ConversationTurns],
        interviewer_message: str,
    ) -> list[ChatMessage]:
        system_parts = [build_identity_card(profile), _CONSTRAINTS]
        if business is not None:
            system_parts.append(
                f"BUSINESS BEING RESEARCHED: {business.name} — {business.description or ''}"
            )
        system_parts.append(f"INTERVIEW OBJECTIVE: {objective}")
        if self._memory is not None:
            memories = await self._memory.retrieve(
                profile.id, interviewer_message, k=self._memory_k
            )
            if memories:
                lines = "\n".join(f"- ({m.kind}) {m.text}" for m in memories)
                system_parts.append(f"YOUR RELEVANT MEMORIES (stay consistent with them):\n{lines}")
        if profile.evidence:
            themes = "\n".join(f"- {e.text[:200]}" for e in profile.evidence[:3])
            system_parts.append(f"BACKGROUND THEMES FROM RESEARCH DATA:\n{themes}")

        messages = [ChatMessage(role="system", content="\n\n".join(system_parts))]
        for turn in prior_turns:  # full history — never silently dropped (R2)
            role = "user" if turn.role == "interviewer" else "assistant"
            messages.append(ChatMessage(role=role, content=turn.content))
        messages.append(ChatMessage(role="user", content=interviewer_message))
        return messages

    async def ask(self, conversation_id: str, interviewer_message: str) -> dict:
        async with self._sessionmaker() as session:
            conversation = await session.get(Conversations, conversation_id)
            if conversation is None:
                raise ConversationNotFound(conversation_id)
            profile = await load_persona(session, conversation.persona_id)
            if profile is None:
                raise PersonaNotFound(conversation.persona_id)
            business = await session.get(Businesses, profile.business_id)
            prior_turns = list(
                (
                    await session.execute(
                        select(ConversationTurns)
                        .where(ConversationTurns.conversation_id == conversation_id)
                        .order_by(ConversationTurns.turn_number)
                    )
                ).scalars()
            )

        messages = await self._compose(
            profile, business, conversation.objective, prior_turns, interviewer_message
        )
        result = await self._llm.complete(
            LLMRequest(
                task=TaskType.PERSONA_INTERVIEW,
                messages=messages,
                max_output_tokens=400,
                temperature=0.7,
                persona_id=profile.id,
                conversation_id=conversation_id,
            )
        )
        reply = result.text.strip()

        next_turn = len(prior_turns) + 1
        async with self._sessionmaker() as session:
            session.add(
                ConversationTurns(
                    id=uuid.uuid4().hex,
                    conversation_id=conversation_id,
                    turn_number=next_turn,
                    role="interviewer",
                    content=interviewer_message,
                )
            )
            session.add(
                ConversationTurns(
                    id=uuid.uuid4().hex,
                    conversation_id=conversation_id,
                    turn_number=next_turn + 1,
                    role="persona",
                    content=reply,
                )
            )
            await session.commit()

        if self._memory is not None:
            await self._memory.remember(
                profile.id,
                f'In an interview I was asked: "{interviewer_message}" and I replied: "{reply}"',
                kind="episodic",
                importance=0.4,
            )

        return {
            "reply": reply,
            "turn_number": next_turn + 1,
            "served_by": f"{result.provider}/{result.model}",
        }
