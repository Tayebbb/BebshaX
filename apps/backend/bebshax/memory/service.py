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
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.llm import ChatMessage, LLMRequest, LLMService, TaskType
from bebshax.llm.adapters.embeddings import EmbeddingBackend
from bebshax.llm.json_utils import parse_llm_json
from bebshax.memory.orm import MEMORY_SOURCES, MemoryItems
from bebshax.memory.scoring import (
    W_IMPORTANCE,
    W_RECENCY,
    W_RELEVANCE,
    combined_score,
    cosine,
)

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


class MemoryRecord(BaseModel):
    id: str
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

    async def remember(
        self,
        persona_id: str,
        text: str,
        kind: str = "episodic",
        importance: float = 0.5,
        *,
        source: str = "persona",
        conversation_id: str | None = None,
    ) -> MemoryRecord:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if source not in SOURCES:
            raise ValueError(f"source must be one of {SOURCES}")
        digest = content_hash(kind, text, source)
        async with self._sessionmaker() as session:
            existing = (
                await session.execute(
                    select(MemoryItems).where(
                        MemoryItems.persona_id == persona_id,
                        MemoryItems.content_hash == digest,
                    )
                )
            ).scalars().first()
            if existing is not None:
                # Identical memory already stored — never a second row.
                return _record(existing)

            [vector] = await self._embeddings.embed([text])
            item = MemoryItems(
                id=uuid.uuid4().hex,
                persona_id=persona_id,
                kind=kind,
                text=text,
                embedding=vector,
                embedding_space=self._embeddings.space,
                importance=max(0.0, min(1.0, importance)),
                source=source,
                conversation_id=conversation_id,
                content_hash=digest,
            )
            session.add(item)
            await session.commit()
        return _record(item)

    async def retrieve(
        self,
        persona_id: str,
        query: str,
        k: int = 6,
        *,
        min_relevance: float = DEFAULT_MIN_RELEVANCE,
        sources: tuple[str, ...] | None = DEFAULT_SOURCES,
    ) -> list[MemoryRecord]:
        """Top-k memories by combined score.

        ``sources`` filters by who produced the text (default: the persona's
        own statements only — interviewer text is never a recollection);
        ``None`` disables the filter. Items whose cosine relevance is below
        ``min_relevance`` are excluded regardless of recency/importance.
        """
        [query_vec] = await self._embeddings.embed([query])
        now = _utcnow()
        w_rel, w_rec, w_imp = self._weights
        async with self._sessionmaker() as session:
            stmt = select(MemoryItems).where(
                MemoryItems.persona_id == persona_id,
                MemoryItems.embedding_space == self._embeddings.space,
            )
            if sources:
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
        self, persona_id: str, batch: int = 12, min_episodic: int = 8
    ) -> list[MemoryRecord]:
        """Distill recent episodic memories into durable reflection items via
        MEMORY_SUMMARIZATION. Best-effort enrichment: parse failures log and
        return [] — reflection must never break a conversation flow.

        Only the persona's OWN statements are distilled: interviewer-sourced
        items would let a researcher author the persona's "insights"."""
        if self._llm is None:
            raise ValueError("MemoryService needs an LLMService for reflect()")
        async with self._sessionmaker() as session:
            episodic = list(
                (
                    await session.execute(
                        select(MemoryItems)
                        .where(
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
                        'first-person insights. Reply STRICT JSON: {"insights": [str, ...]}'
                    ),
                ),
                ChatMessage(role="user", content=observations),
            ],
            json_mode=True,
            max_output_tokens=300,
            persona_id=persona_id,
        )
        result = await self._llm.complete(request)
        try:
            parsed = parse_llm_json(result.text)
            insights = parsed.get("insights", []) if isinstance(parsed, dict) else []
        except ValueError:
            logger.warning("reflection output unparseable for persona %s — skipped", persona_id)
            return []

        stored: list[MemoryRecord] = []
        for insight in insights[:3]:
            if isinstance(insight, str) and insight.strip():
                stored.append(
                    await self.remember(
                        persona_id, insight.strip(), kind="reflection", importance=0.8
                    )
                )
        return stored

    async def list_for_persona(
        self,
        persona_id: str,
        kind: str | None = None,
        limit: int = 50,
        *,
        sources: tuple[str, ...] | None = DEFAULT_SOURCES,
    ) -> list[MemoryRecord]:
        """Newest-first listing. Defaults to the persona's own statements —
        interviewer questions are context, never something the persona
        "remembers"; pass ``sources=None`` to include everything."""
        async with self._sessionmaker() as session:
            query = select(MemoryItems).where(MemoryItems.persona_id == persona_id)
            if kind:
                query = query.where(MemoryItems.kind == kind)
            if sources:
                query = query.where(MemoryItems.source.in_(tuple(sources)))
            query = query.order_by(MemoryItems.created_at.desc()).limit(limit)
            rows = list((await session.execute(query)).scalars().all())

        return [_record(row) for row in rows]
