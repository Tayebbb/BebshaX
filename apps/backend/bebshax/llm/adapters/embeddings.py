"""Embedding backends (R1 boundary module — may import freellmpool).

Space consistency rule: cosine similarity is only meaningful between vectors
from the SAME embedding space. Every backend declares a `space` tag stored
next to each vector; retrieval filters candidates to the query's space.

Default backend is the deterministic local hash embedding: zero network, zero
cost, stable across restarts and machines. Remote embeddings require an
explicitly pinned Freellmpool model and a separate embedding space.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import threading
import time
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx
from freellmpool.client import HTTPResult

from bebshax.llm.adapters.provider_policy import approved_primary_providers
from bebshax.llm.adapters.freellmpool_transport import AttemptQuota
from bebshax.llm.adapters.openrouter_adapter import _map_http_status
from bebshax.llm.embedding_space import CANONICAL_DIM
from bebshax.llm.estimator import SAFETY_MARGIN, estimate_text_tokens
from bebshax.llm.failures import FAILURE_POLICIES
from bebshax.llm.governance import RemoteProcessingPolicy, get_llm_request_context
from bebshax.llm.retry import retry_after_hint


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
    """One approved native embedding space, with worker-owned sync transport."""

    def __init__(
        self, model: str, pool=None, *, provider_config: Path | None = None,
        transport: httpx.BaseTransport | None = None, timeout_s: float = 30.0,
        processing_policy: RemoteProcessingPolicy | None = None,
    ) -> None:
        if not model:
            raise ValueError("FreellmpoolEmbedding requires a pinned model name")
        if pool is not None:
            raise ValueError("Unmanaged embedding pools bypass policy; inject an HTTP transport instead")
        if processing_policy is None:
            raise ValueError("Remote embeddings require an explicit processing policy")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("Embedding timeout must be finite and positive")
        self._model = model
        self._provider_id: str | None = None
        self._quota: AttemptQuota | None = None
        self._rpd = 0
        self._cooldown_until = 0.0
        self._processing_policy = processing_policy
        self._timeout_s = timeout_s
        self._deadline = 0.0
        self._context_window = 0
        self._pool = None
        self._provider_config = provider_config or Path(__file__).resolve().parents[5] / "providers.toml"
        self._transport = transport
        self._client: httpx.Client | None = None
        self._space: str | None = None
        self._url: str | None = None
        self._lock = asyncio.Lock()
        self._pending: set[asyncio.Task[list[list[float]]]] = set()
        self._closing: asyncio.Task[None] | None = None
        self._closed = False
        self._cancelled = threading.Event()
        self._inputs: list[str] = []

    @property
    def space(self) -> str:
        self._get_pool()
        assert self._space is not None
        return self._space

    def _get_pool(self):
        if self._pool is None:
            from freellmpool import Pool
            from freellmpool import config as fl_config
            from freellmpool.quota import QuotaStore

            try:
                catalog = fl_config.load_catalog(self._provider_config)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                raise ValueError("Embedding provider policy catalog is unavailable or invalid") from exc
            approved = approved_primary_providers(catalog)
            names = {name for provider in approved for name in (provider.key_env, *provider.extra_env) if name}
            env = {name: os.environ[name] for name in names if name in os.environ}
            configured = [
                replace(provider, models=tuple(model for model in provider.models if model.name == self._model))
                for provider in approved
                if provider.adapter in {"openai", "cloudflare"}
                and provider.is_configured(env)
                and any(model.name == self._model for model in provider.models)
            ]
            if len(configured) != 1:
                raise ValueError("Embedding provider policy must pin exactly one approved configured destination and model")
            [provider] = configured
            self._provider_id = provider.id
            context_window = provider.models[0].context
            if type(context_window) is not int or context_window <= 0:
                raise ValueError("Embedding policy requires a verified positive context window")
            self._context_window = context_window
            self._rpd = provider.models[0].rpd
            self._space = f"freellmpool:{provider.id}:{self._model}:native-{self.dim}"
            self._url = provider.base_url.replace("{account_id}", env.get("CLOUDFLARE_ACCOUNT_ID", "")) + "/embeddings"
            self._quota = AttemptQuota(
                QuotaStore(path=self._provider_config.parent / ".cache" / "embedding-quota.json"), account_on_success=False,
            )
            self._pool = Pool(
                configured, embedders=configured, env=env, cache=None,
                post=self._post, quota=self._quota,
            )
        return self._pool

    def _post(self, url: str, headers: dict, body: dict, timeout: float) -> HTTPResult:
        if self._cancelled.is_set():
            raise asyncio.CancelledError()
        remaining = min(timeout, self._deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("Embedding deadline expired before dispatch")
        if url != self._url or body.get("model") != self._model or body.get("input") != self._inputs:
            raise ValueError("Embedding dispatch does not match the approved model and destination policy")
        if time.monotonic() < self._cooldown_until:
            raise ValueError("Embedding provider is cooling until its recovery deadline")
        if self._quota is None or self._provider_id is None:
            raise RuntimeError("Embedding quota policy is not initialized")
        if not self._quota.reserve(self._provider_id, self._model, self._rpd):
            raise ValueError("Embedding daily model allowance is exhausted")
        if self._client is None:
            self._client = httpx.Client(transport=self._transport, follow_redirects=False, trust_env=False)
        response = self._client.post(url, headers=headers, json=body, timeout=remaining)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200:
            policy = FAILURE_POLICIES[_map_http_status(response.status_code, response.text)]
            hint = retry_after_hint(response.headers, payload)
            if policy.cooldown_route or hint is not None:
                seconds = max(policy.cooldown_seconds or 60.0, hint or 0.0)
                self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)
        if self._cancelled.is_set():
            raise asyncio.CancelledError()
        if time.monotonic() >= self._deadline:
            raise TimeoutError("Embedding deadline expired while receiving the response")
        if response.status_code == 200:
            if not isinstance(payload, dict) or payload.get("model", self._model) != self._model:
                raise ValueError("Embedding response changed the pinned model space")
            rows = payload.get("data")
            if not isinstance(rows, list) or len(rows) != len(self._inputs):
                raise ValueError("Embedding response vector count does not match input count")
            indices = [row.get("index") for row in rows if isinstance(row, dict)]
            if len(indices) != len(rows) or any(type(index) is not int for index in indices) or sorted(indices) != list(range(len(rows))):
                raise ValueError("Embedding response vector indices are invalid")
            payload["data"] = sorted(rows, key=lambda row: row["index"])
        return HTTPResult(response.status_code, payload, response.text, dict(response.headers))

    async def _embed_owned(
        self, texts: list[str], cancelled: threading.Event, deadline: float,
    ) -> list[list[float]]:
        async with self._lock:
            if cancelled.is_set():
                raise asyncio.CancelledError()
            pool = self._get_pool()
            context = get_llm_request_context()
            if context is None or self._processing_policy is None:
                raise ValueError("Remote embedding processing requires trusted server request context")
            allowed = self._processing_policy.allowed_providers(context.data_classification)
            if "freellmpool" not in allowed or self._provider_id not in allowed:
                raise ValueError("Embedding processing destination is not approved by server policy")
            if any(math.ceil(estimate_text_tokens(text) * (1 + SAFETY_MARGIN)) > self._context_window for text in texts):
                raise ValueError("Embedding input exceeds the verified context window; truncation is forbidden")
            self._cancelled = cancelled
            self._deadline = deadline
            self._inputs = texts
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Embedding deadline expired during admission")
            reply = await asyncio.to_thread(pool.embed, texts, model=self._model, timeout=remaining)
            if time.monotonic() >= deadline:
                raise TimeoutError("Embedding deadline expired")
            if reply.model != self._model or len(reply.vectors) != len(texts):
                raise ValueError("Embedding response model or vector count does not match the pinned space")
            vectors = []
            for vector in reply.vectors:
                if len(vector) != self.dim:
                    raise ValueError(f"Embedding vector dimension must be {self.dim}; resizing is forbidden")
                if any(type(value) not in {int, float} or not math.isfinite(value) for value in vector):
                    raise ValueError("Embedding vector values must be finite numbers")
                norm = math.hypot(*vector)
                if not math.isfinite(norm) or norm == 0:
                    raise ValueError("Embedding vector must have a finite nonzero norm")
                vectors.append([value / norm for value in vector])
            return vectors

    def _worker_done(self, task: asyncio.Task[list[list[float]]]) -> None:
        self._pending.discard(task)
        if not task.cancelled():
            task.exception()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._closed:
            raise RuntimeError("Embedding backend is closed")
        if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
            raise ValueError("Embedding inputs must be a list of complete texts")
        if not texts:
            return []
        cancelled = threading.Event()
        deadline = asyncio.get_running_loop().time() + self._timeout_s
        task = asyncio.create_task(self._embed_owned(list(texts), cancelled, deadline))
        self._pending.add(task)
        task.add_done_callback(self._worker_done)
        try:
            async with asyncio.timeout_at(deadline):
                return await asyncio.shield(task)
        except (asyncio.CancelledError, TimeoutError):
            cancelled.set()
            raise

    async def _finish_close(self) -> None:
        await asyncio.gather(*self._pending, return_exceptions=True)
        if self._client is not None:
            await asyncio.to_thread(self._client.close)

    async def aclose(self) -> None:
        self._closed = True
        if self._closing is None:
            self._closing = asyncio.create_task(self._finish_close())
        await asyncio.shield(self._closing)
