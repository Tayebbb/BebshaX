"""Semantic vector storage and retrieval for evidence chunks via pgvector.

Generates 384-dimensional normalized embeddings and performs cosine similarity search.
"""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import EvidenceChunks
from bebshax.llm.adapters.embeddings import (
    CANONICAL_DIM,
    EmbeddingBackend,
    HashEmbedding,
)


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two float vectors in Python."""
    if not vec1 or not vec2:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if not norm1 or not norm2:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


class VectorSearchEngine:
    def __init__(self, backend: Optional[EmbeddingBackend] = None) -> None:
        self.backend = backend or HashEmbedding()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate 384-dimensional normalized vector embeddings."""
        return await self.backend.embed(texts)

    async def search_chunks(
        self,
        session: AsyncSession,
        study_id: str,
        query_text: str,
        top_k: int = 6,
    ) -> list[tuple[EvidenceChunks, float]]:
        """Retrieve the top-K most semantically relevant chunks for a study."""
        if not query_text or not query_text.strip():
            return []

        query_vectors = await self.backend.embed([query_text])
        query_vec = query_vectors[0]

        bind = session.bind or session.get_bind()
        dialect_name = bind.dialect.name if bind else "postgresql"

        # On PostgreSQL with pgvector, use native vector cosine distance
        if dialect_name == "postgresql":
            try:
                distance_col = EvidenceChunks.embedding.cosine_distance(query_vec)
                stmt = (
                    select(EvidenceChunks, distance_col.label("distance"))
                    .where(EvidenceChunks.study_id == study_id)
                    .order_by(distance_col)
                    .limit(top_k)
                )
                result = await session.execute(stmt)
                rows = result.all()
                return [(chunk, round(max(0.0, 1.0 - float(dist)), 3)) for chunk, dist in rows]
            except Exception:
                pass  # Fallback to Python-side scoring if pgvector function isn't bound

        # Python-side fallback (used during in-memory SQLite unit tests)
        stmt = select(EvidenceChunks).where(EvidenceChunks.study_id == study_id)
        result = await session.execute(stmt)
        all_chunks = list(result.scalars().all())

        scored: list[tuple[EvidenceChunks, float]] = []
        for chunk in all_chunks:
            chunk_vec = chunk.embedding
            if isinstance(chunk_vec, list) and len(chunk_vec) == CANONICAL_DIM:
                sim = _cosine_similarity(query_vec, chunk_vec)
                scored.append((chunk, round(sim, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
