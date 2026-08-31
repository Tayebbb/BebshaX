"""MemoryService: write, retrieve (relevance+recency+importance), reflect."""

from __future__ import annotations

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
from bebshax.memory.orm import MemoryItems
from bebshax.memory.scoring import (
    W_IMPORTANCE,
    W_RECENCY,
    W_RELEVANCE,
    combined_score,
    cosine,
)

logger = logging.getLogger(__name__)

KINDS = ("episodic", "semantic", "reflection")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRecord(BaseModel):
    id: str
    persona_id: str
    kind: str
    text: str
    importance: float
    created_at: datetime
    score: float | None = None  # populated on retrieval


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
    ) -> MemoryRecord:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        [vector] = await self._embeddings.embed([text])
        item = MemoryItems(
            id=uuid.uuid4().hex,
            persona_id=persona_id,
            kind=kind,
            text=text,
            embedding=vector,
            embedding_space=self._embeddings.space,
            importance=max(0.0, min(1.0, importance)),
        )
        async with self._sessionmaker() as session:
            session.add(item)
            await session.commit()
        return MemoryRecord(
            id=item.id,
            persona_id=persona_id,
            kind=kind,
            text=text,
            importance=item.importance,
            created_at=item.created_at,
        )

    async def retrieve(self, persona_id: str, query: str, k: int = 6) -> list[MemoryRecord]:
        [query_vec] = await self._embeddings.embed([query])
        now = _utcnow()
        w_rel, w_rec, w_imp = self._weights
        async with self._sessionmaker() as session:
            rows = list(
                (
                    await session.execute(
                        select(MemoryItems).where(
                            MemoryItems.persona_id == persona_id,
                            MemoryItems.embedding_space == self._embeddings.space,
                        )
                    )
                ).scalars()
            )
            scored: list[tuple[float, MemoryItems]] = []
            for row in rows:
                created = row.created_at
                if created.tzinfo is None:  # sqlite returns naive datetimes
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (now - created).total_seconds() / 3600)
                score = combined_score(
                    cosine(query_vec, list(row.embedding)),
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
        return [
            MemoryRecord(
                id=row.id,
                persona_id=row.persona_id,
                kind=row.kind,
                text=row.text,
                importance=row.importance,
                created_at=row.created_at,
                score=round(score, 6),
            )
            for score, row in top
        ]

    async def reflect(
        self, persona_id: str, batch: int = 12, min_episodic: int = 8
    ) -> list[MemoryRecord]:
        """Distill recent episodic memories into durable reflection items via
        MEMORY_SUMMARIZATION. Best-effort enrichment: parse failures log and
        return [] — reflection must never break a conversation flow."""
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
        self, persona_id: str, kind: str | None = None, limit: int = 50
    ) -> list[MemoryRecord]:
        async with self._sessionmaker() as session:
            query = select(MemoryItems).where(MemoryItems.persona_id == persona_id)
            if kind:
                query = query.where(MemoryItems.kind == kind)
            query = query.order_by(MemoryItems.created_at.desc()).limit(limit)
            rows = list((await session.execute(query)).scalars().all())

        return [
            MemoryRecord(
                id=row.id,
                persona_id=row.persona_id,
                kind=row.kind,
                text=row.text,
                importance=row.importance,
                created_at=row.created_at,
            )
            for row in rows
        ]
