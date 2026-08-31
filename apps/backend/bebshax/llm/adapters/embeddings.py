"""Embedding backends (R1 boundary module — may import freellmpool).

Space consistency rule: cosine similarity is only meaningful between vectors
from the SAME embedding space. Every backend declares a `space` tag stored
next to each vector; retrieval filters candidates to the query's space.

Default backend is the deterministic local hash embedding: zero network, zero
cost, stable across restarts and machines — the right reliability trade-off
for a free-tier project (semantics are lexical-strength; upgrade paths are
the pinned freellmpool backend, the local Ollama backend, or "auto" — all
per-deployment via BEBSHAX_EMBEDDING_*).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
from abc import ABC, abstractmethod
from collections import Counter

import httpx

logger = logging.getLogger(__name__)

CANONICAL_DIM = 384

DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


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


class OllamaEmbedding(EmbeddingBackend):
    """Semantic embeddings from a local Ollama model via the native
    ``/api/embed`` endpoint — plain httpx, no SDK (R8).

    Vectors are fitted to CANONICAL_DIM and re-normalized (same contract as
    FreellmpoolEmbedding) so they fit the Vector(384) columns; the space tag
    pins model + stored dim so spaces never mix (":tag" suffixes are dropped —
    ``nomic-embed-text`` and ``nomic-embed-text:latest`` are the same weights).
    """

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_EMBED_MODEL,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        request_timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._base_url = base_url or os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_BASE_URL)
        self._client = client
        self._request_timeout = request_timeout
        self.space = f"ollama-{model.split(':', 1)[0]}-{CANONICAL_DIM}"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._get_client().post(
            "/api/embed",
            json={"model": self._model, "input": texts},
            timeout=self._request_timeout,
        )
        resp.raise_for_status()
        vectors = resp.json().get("embeddings") or []
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"ollama /api/embed returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        return [fit_dim([float(x) for x in vec], self.dim) for vec in vectors]


class AutoEmbedding(EmbeddingBackend):
    """Resolves to OllamaEmbedding or HashEmbedding on first use.

    Probes ``GET /api/tags`` lazily (short timeout, once, cached) — Ollama up
    AND the embed model pulled → semantic Ollama embeddings; anything else →
    deterministic hash embeddings with ONE warning naming the space in use.
    ``space`` is only readable after the first ``embed()`` call, which is safe:
    every persisted row obtains its vector from ``embed()`` before its space
    tag is read.
    """

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_EMBED_MODEL,
        base_url: str | None = None,
        probe_timeout: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url or os.environ.get("OLLAMA_API_BASE", DEFAULT_OLLAMA_BASE_URL)
        self._probe_timeout = probe_timeout
        self._client = client  # injectable for tests; reused by the Ollama delegate
        self._delegate: EmbeddingBackend | None = None
        self._lock = asyncio.Lock()

    @property
    def space(self) -> str:  # type: ignore[override]
        if self._delegate is None:
            raise RuntimeError(
                "auto embedding backend unresolved — call embed() before reading .space"
            )
        return self._delegate.space

    async def _resolve(self) -> EmbeddingBackend:
        if self._delegate is not None:
            return self._delegate
        async with self._lock:
            if self._delegate is not None:
                return self._delegate
            self._delegate = await self._probe()
            return self._delegate

    async def _probe(self) -> EmbeddingBackend:
        wanted = self._model.split(":", 1)[0]
        try:
            client = self._client or httpx.AsyncClient(base_url=self._base_url)
            owns_client = self._client is None
            try:
                resp = await client.get("/api/tags", timeout=self._probe_timeout)
                resp.raise_for_status()
                available = {
                    (m.get("name") or "").split(":", 1)[0]
                    for m in resp.json().get("models", [])
                }
            finally:
                if owns_client:
                    await client.aclose()
            if wanted in available:
                delegate = OllamaEmbedding(
                    self._model, base_url=self._base_url, client=self._client
                )
                logger.info("embedding backend auto-resolved to Ollama (space=%s)", delegate.space)
                return delegate
            fallback = HashEmbedding()
            logger.warning(
                "Ollama is up but embed model %r is not pulled — using deterministic "
                "hash embeddings (space=%s)",
                self._model,
                fallback.space,
            )
            return fallback
        except Exception:
            fallback = HashEmbedding()
            logger.warning(
                "Ollama unreachable — using deterministic hash embeddings (space=%s)",
                fallback.space,
            )
            return fallback

    async def embed(self, texts: list[str]) -> list[list[float]]:
        delegate = await self._resolve()
        return await delegate.embed(texts)
