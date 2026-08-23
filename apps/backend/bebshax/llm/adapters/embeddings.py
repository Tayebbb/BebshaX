"""Embedding backends (R1 boundary module — may import freellmpool).

Space consistency rule: cosine similarity is only meaningful between vectors
from the SAME embedding space. Every backend declares a `space` tag stored
next to each vector; retrieval filters candidates to the query's space.

Default backend is the deterministic local hash embedding: zero network, zero
cost, stable across restarts and machines — the right reliability trade-off
for a free-tier project (semantics are lexical-strength; upgrade path is the
pinned freellmpool backend below, per-deployment via BEBSHAX_EMBEDDING_*).
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from abc import ABC, abstractmethod
from collections import Counter

CANONICAL_DIM = 384


def fit_dim(vector: list[float], dim: int = CANONICAL_DIM) -> list[float]:
    """Truncate/zero-pad to the canonical dim, then L2-normalize. Within one
    pinned model space this keeps vectors self-consistent."""
    vec = list(vector[:dim]) + [0.0] * max(0, dim - len(vector))
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


class EmbeddingBackend(ABC):
    space: str
    dim: int = CANONICAL_DIM

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized `dim`-sized vector per input text."""


class HashEmbedding(EmbeddingBackend):
    """Deterministic bag-of-tokens feature hashing. Offline, dependency-free."""

    space = f"local-hash-{CANONICAL_DIM}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = [t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(t) > 2]
        for token, count in Counter(tokens).items():
            digest = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            index = digest % self.dim
            sign = 1.0 if (digest >> 63) & 1 else -1.0
            vec[index] += sign * (1.0 + math.log(count))
        return fit_dim(vec, self.dim)


class FreellmpoolEmbedding(EmbeddingBackend):
    """Remote embeddings with freellmpool's provider failover, PINNED to one
    model so all vectors share a space. Sync Pool.embed is bridged via a
    thread + lock (freellmpool has no async embed; its sync client is not
    thread-safe, so calls are serialized)."""

    def __init__(self, model: str, pool=None) -> None:
        if not model:
            raise ValueError("FreellmpoolEmbedding requires a pinned model name")
        self._model = model
        self._pool = pool
        self._lock = asyncio.Lock()
        self.space = f"freellmpool:{model}"

    def _get_pool(self):
        if self._pool is None:
            from freellmpool import Pool

            self._pool = Pool.from_default_config()
        return self._pool

    async def embed(self, texts: list[str]) -> list[list[float]]:
        pool = self._get_pool()
        async with self._lock:
            reply = await asyncio.to_thread(pool.embed, texts, model=self._model)
        return [fit_dim(list(vec), self.dim) for vec in reply.vectors]
