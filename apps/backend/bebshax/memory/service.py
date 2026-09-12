"""MemoryService: write, retrieve (relevance+recency+importance), reflect.

Poisoning defences (red-team fix): every item carries a ``source``; retrieval
defaults to the persona's OWN statements, so text typed by a researcher can be
stored for audit but never comes back as a "recollection". Identical
write-backs dedupe on (persona_id, sha256(kind+text)), and a cosine floor
drops memories that merely happen to be recent/important.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.llm import ChatMessage, LLMError, LLMRequest, LLMService, TaskType
from bebshax.llm.adapters.embeddings import EmbeddingBackend
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.placeholders import is_placeholder
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.memory.orm import MEMORY_SOURCES, MemoryItems
from bebshax.persona.context import private_persona_context
from bebshax.memory.scoring import (
    W_IMPORTANCE,
    W_RECENCY,
    W_RELEVANCE,
    combined_score,
    cosine,
)
from bebshax.tenancy import PUBLIC_OWNER_IDS

logger = logging.getLogger(__name__)

KINDS = ("episodic", "semantic", "reflection")
SOURCES = MEMORY_SOURCES

# Cosine floor for retrieval. With the default HashEmbedding (signed
# bag-of-tokens, 384 dims) two texts that share NO token score ≈0 ± collision
# noise, where each accidental bucket collision contributes about
# 1/sqrt(|q|·|m|) (≈0.03–0.05 for a 6–10 token question against a 20–40
# token memory). Texts that share even one real token score ≥ 1/sqrt(|q|·|m|)
# ≈ 0.05–0.15 at those lengths, so 0.05 separates "unrelated" from "related"
# without a stoplist. It is deliberately NOT higher: a single shared content
# word between a short question and a long reply already sits near 0.06.
DEFAULT_MIN_RELEVANCE = 0.05
DEFAULT_SOURCES: tuple[str, ...] = ("persona",)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(kind: str, text: str, source: str = "persona") -> str:
    """Stable dedupe key: same source + kind + text ⇒ same memory.

    ``source`` is part of the key so a researcher's question can never shadow
    the persona's own identical statement (which must stay retrievable).
    """
    return hashlib.sha256(f"{source}\x1f{kind}\x1f{text}".encode("utf-8")).hexdigest()


def require_owner_id(owner_id: str | None) -> str:
    if (not isinstance(owner_id, str) or not owner_id.strip()
            or owner_id in PUBLIC_OWNER_IDS or len(owner_id) > 64):
        raise ValueError("memory requires a verified owner_id")
    return owner_id


def validate_memory_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("memory text cannot be empty")
    if is_placeholder(text) or re.fullmatch(r"\{\{[^{}]+\}\}", text.strip()):
        raise ValueError("memory text cannot be a placeholder")


@dataclass(frozen=True)
class PreparedMemoryText:
    text: str
    embedding: tuple[float, ...]
    embedding_space: str


class MemoryRecord(BaseModel):
    id: str
    owner_id: str | None = None
    persona_id: str
    kind: str
    text: str
    importance: float
    created_at: datetime
    source: str = "persona"
    conversation_id: str | None = None
    score: float | None = None  # populated on retrieval


def _record(row: MemoryItems, score: float | None = None) -> MemoryRecord:
    return MemoryRecord(
        id=row.id,
        owner_id=row.owner_id,
        persona_id=row.persona_id,
        kind=row.kind,
        text=row.text,
        importance=row.importance,
        created_at=row.created_at,
        source=row.source or "persona",
        conversation_id=row.conversation_id,
        score=None if score is None else round(score, 6),
    )


class MemoryService:
    def __init__(
        self,
        sessionmaker_: sessionmaker[AsyncSession],
        embeddings: EmbeddingBackend,
        llm: LLMService | None = None,
        w_rel: float = W_RELEVANCE,
        w_rec: float = W_RECENCY,
        w_imp: float = W_IMPORTANCE,
    ) -> None:
        self._sessionmaker = sessionmaker_
        self._embeddings = embeddings
        self._llm = llm  # required only for reflect()
        self._weights = (w_rel, w_rec, w_imp)

    async def _resolve_owner(
        self, persona_id: str, owner_id: str | None, conversation_id: str | None,
        session: AsyncSession | None = None,
    ) -> str:
        if conversation_id is None:
            return require_owner_id(owner_id)
        from bebshax.interview.orm import Conversations

        async with (nullcontext(session) if session is not None else self._sessionmaker()) as read_session:
            conversation = await read_session.get(Conversations, conversation_id)
            if conversation is None or conversation.persona_id != persona_id:
                raise ValueError("memory conversation must belong to the requested persona")
            verified_owner = require_owner_id(conversation.user_id)
            if owner_id is not None and owner_id != verified_owner:
                raise ValueError("memory owner does not match conversation owner")
            return verified_owner

    async def prepare(self, texts: list[str]) -> list[PreparedMemoryText]:
        """Embed full validated texts before entering a transaction that holds locks."""
        for text in texts:
            validate_memory_text(text)
        vectors = await self._embeddings.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError("embedding service returned an incomplete memory batch")
        return [PreparedMemoryText(text, tuple(vector), self._embeddings.space)
                for text, vector in zip(texts, vectors, strict=True)]

    async def remember(
        self,
        persona_id: str,
        text: str,
        kind: str = "episodic",
        importance: float = 0.5,
        *,
        owner_id: str | None = None,
        source: str = "persona",
        conversation_id: str | None = None,
        session: AsyncSession | None = None,
        prepared: PreparedMemoryText | None = None,
    ) -> MemoryRecord:
        """Flush into a caller's session, or commit an independently owned session."""
        owner_id = await self._resolve_owner(persona_id, owner_id, conversation_id, session)
        validate_memory_text(text)
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}")
        if prepared is None:
            [prepared] = await self.prepare([text])
        elif prepared.text != text:
            raise ValueError("prepared memory text does not match the full payload")
        digest = content_hash(kind, text, source)
        async with (nullcontext(session) if session is not None else self._sessionmaker()) as write_session:
            existing = (
                await write_session.execute(
                    select(MemoryItems).where(
                        MemoryItems.owner_id == owner_id,
                        MemoryItems.persona_id == persona_id,
                        or_(
                            MemoryItems.content_hash == digest,
                            (MemoryItems.content_hash.is_(None)
                             & (MemoryItems.kind == kind) & (MemoryItems.source == source)
                             & (MemoryItems.text == text)),
                        ),
                    )
                )
            ).scalars().first()
            if existing is not None:
                return _record(existing)

            item = MemoryItems(
                id=uuid.uuid4().hex,
                owner_id=owner_id,
                persona_id=persona_id,
                kind=kind,
                text=text,
                embedding=list(prepared.embedding),
                embedding_space=prepared.embedding_space,
                importance=max(0.0, min(1.0, importance)),
                source=source,
                conversation_id=conversation_id,
                content_hash=digest,
            )
            dialect = write_session.get_bind().dialect.name
            if dialect in {"postgresql", "sqlite"}:
                insert = postgresql_insert if dialect == "postgresql" else sqlite_insert
                inserted_id = await write_session.scalar(
                    insert(MemoryItems).values(
                        id=item.id, owner_id=owner_id, persona_id=persona_id,
                        kind=kind, text=text, embedding=item.embedding,
                        embedding_space=item.embedding_space, importance=item.importance,
                        source=source, conversation_id=conversation_id, content_hash=digest,
                        created_at=_utcnow(),
                    ).on_conflict_do_nothing(
                        index_elements=["owner_id", "persona_id", "content_hash"],
                    ).returning(MemoryItems.id)
                )
                item = await write_session.get(MemoryItems, inserted_id) if inserted_id else None
            else:
                try:
                    async with write_session.begin_nested():
                        write_session.add(item)
                        await write_session.flush()
                except IntegrityError:
                    item = None
            if item is None:
                existing = (await write_session.execute(select(MemoryItems).where(
                    MemoryItems.owner_id == owner_id,
                    MemoryItems.persona_id == persona_id,
                    MemoryItems.content_hash == digest,
                ))).scalar_one_or_none()
                if existing is None:
                    raise RuntimeError("memory write could not be verified after conflict")
                return _record(existing)
            record = _record(item)
            if session is None:
                await write_session.commit()
            return record

    async def retrieve(
        self,
        persona_id: str,
        query: str,
        k: int = 6,
        *,
        owner_id: str | None = None,
        conversation_id: str | None = None,
        min_relevance: float = DEFAULT_MIN_RELEVANCE,
        sources: tuple[str, ...] | None = DEFAULT_SOURCES,
    ) -> list[MemoryRecord]:
        """Top-k memories by combined score.

        ``sources`` filters by who produced the text (default: the persona's
        own statements only — interviewer text is never a recollection);
        ``None`` disables the filter. Items whose cosine relevance is below
        ``min_relevance`` are excluded regardless of recency/importance.
        """
        owner_id = await self._resolve_owner(persona_id, owner_id, conversation_id)
        [query_vec] = await self._embeddings.embed([query])
        now = _utcnow()
        w_rel, w_rec, w_imp = self._weights
        async with self._sessionmaker() as session:
            stmt = select(MemoryItems).where(
                MemoryItems.owner_id == owner_id,
                MemoryItems.persona_id == persona_id,
                MemoryItems.embedding_space == self._embeddings.space,
            )
            if sources is not None:
                stmt = stmt.where(MemoryItems.source.in_(tuple(sources)))
            rows = list((await session.execute(stmt)).scalars())
            scored: list[tuple[float, MemoryItems]] = []
            for row in rows:
                relevance = cosine(query_vec, list(row.embedding))
                if relevance < min_relevance:
                    continue
                created = row.created_at
                if created.tzinfo is None:  # sqlite returns naive datetimes
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (now - created).total_seconds() / 3600)
                score = combined_score(
                    relevance,
                    age_hours,
                    row.importance,
                    w_rel,
                    w_rec,
                    w_imp,
                )
                scored.append((score, row))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            top = scored[:k]
            for _, row in top:
                row.last_accessed = now
            await session.commit()
        return [_record(row, score) for score, row in top]

    async def reflect(
        self, persona_id: str, batch: int = 12, min_episodic: int = 8,
        *, owner_id: str | None = None, conversation_id: str | None = None,
    ) -> list[MemoryRecord]:
        """Distill recent episodic memories into durable reflection items via
        MEMORY_SUMMARIZATION. Best-effort enrichment: parse failures log and
        return [] — reflection must never break a conversation flow.

        Only the persona's OWN statements are distilled: interviewer-sourced
        items would let a researcher author the persona's "insights"."""
        owner_id = await self._resolve_owner(persona_id, owner_id, conversation_id)
        if self._llm is None:
            raise ValueError("MemoryService needs an LLMService for reflect()")
        study_id = None
        async with self._sessionmaker() as session:
            if conversation_id is not None:
                from bebshax.interview.orm import Conversations

                conversation = await session.get(Conversations, conversation_id)
                if (conversation is None or conversation.persona_id != persona_id
                        or conversation.user_id != owner_id):
                    raise ValueError("Reflection conversation no longer belongs to this owner and persona.")
                study_id = conversation.study_id
            episodic = list(
                (
                    await session.execute(
                        select(MemoryItems)
                        .where(
                            MemoryItems.owner_id == owner_id,
                            MemoryItems.persona_id == persona_id,
                            MemoryItems.kind == "episodic",
                            MemoryItems.source == "persona",
                        )
                        .order_by(MemoryItems.created_at.desc())
                        .limit(batch)
                    )
                ).scalars()
            )
        if len(episodic) < min_episodic:
            return []

        observations = "\n".join(f"- {row.text}" for row in reversed(episodic))
        request = LLMRequest(
            task=TaskType.MEMORY_SUMMARIZATION,
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "Distill the persona's observations into at most 3 durable, "
                        'first-person insights. Reply STRICT JSON: {"insights": [str, ...]} '
                        + UNTRUSTED_RULE
                    ),
                ),
                ChatMessage(role="user", content=untrusted_block("OBSERVATIONS", observations, source="persona memories")),
            ],
            json_mode=True,
            # Distillation is a summarising task: low temperature keeps the
            # insights anchored to what was actually said.
            temperature=0.3,
            max_output_tokens=300,
            persona_id=persona_id,
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            study_id=study_id,
            data_classification="private",
        )
        try:
            with private_persona_context(owner_id, study_id):
                result = await self._llm.complete(request)
        except LLMError as exc:
            logger.info("reflection unavailable for persona %s: %s", persona_id, type(exc).__name__)
            return []
        try:
            parsed = parse_llm_json(result.text)
            insights = parsed.get("insights", []) if isinstance(parsed, dict) else []
        except ValueError:
            logger.warning("reflection output unparseable for persona %s — skipped", persona_id)
            return []

        reflection_texts = [
            insight.strip() for insight in insights[:3]
            if isinstance(insight, str) and insight.strip()
        ]
        if not reflection_texts:
            return []
        prepared_memories = await self.prepare(reflection_texts)
        stored: list[MemoryRecord] = []
        async with self._sessionmaker() as session, session.begin():
            for prepared in prepared_memories:
                stored.append(
                    await self.remember(
                        persona_id, prepared.text, kind="reflection", importance=0.8,
                        owner_id=owner_id, conversation_id=conversation_id,
                        session=session, prepared=prepared,
                    )
                )
        return stored

    async def list_for_persona(
        self,
        persona_id: str,
        kind: str | None = None,
        limit: int = 50,
        *,
        owner_id: str | None = None,
        conversation_id: str | None = None,
        sources: tuple[str, ...] | None = DEFAULT_SOURCES,
    ) -> list[MemoryRecord]:
        """Newest-first listing. Defaults to the persona's own statements —
        interviewer questions are context, never something the persona
        "remembers"; pass ``sources=None`` to include everything."""
        owner_id = await self._resolve_owner(persona_id, owner_id, conversation_id)
        async with self._sessionmaker() as session:
            query = select(MemoryItems).where(
                MemoryItems.owner_id == owner_id, MemoryItems.persona_id == persona_id
            )
            if kind:
                query = query.where(MemoryItems.kind == kind)
            if sources is not None:
                query = query.where(MemoryItems.source.in_(tuple(sources)))
            query = query.order_by(MemoryItems.created_at.desc()).limit(limit)
            rows = list((await session.execute(query)).scalars().all())

        return [_record(row) for row in rows]
