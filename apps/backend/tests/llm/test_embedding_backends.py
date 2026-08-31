"""Unit tests for the Ollama + auto embedding backends (Task D2).

All HTTP is faked via httpx.MockTransport — no live network, per R7.
"""

from __future__ import annotations

import httpx
import pytest

from bebshax.llm.adapters.embeddings import (
    CANONICAL_DIM,
    AutoEmbedding,
    HashEmbedding,
    OllamaEmbedding,
)
from bebshax.llm.adapters.factory import build_embedding_backend


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://fake-ollama:11434", transport=httpx.MockTransport(handler)
    )


def _tags_response(models: list[str]) -> httpx.Response:
    return httpx.Response(200, json={"models": [{"name": m} for m in models]})


def _embed_response(count: int, dim: int) -> httpx.Response:
    return httpx.Response(200, json={"embeddings": [[0.5] * dim for _ in range(count)]})


class TestOllamaEmbedding:
    @pytest.mark.asyncio
    async def test_embed_fits_vectors_to_canonical_dim_and_normalizes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/embed"
            return _embed_response(count=2, dim=768)  # native nomic dim > canonical

        backend = OllamaEmbedding("nomic-embed-text", client=_client(handler))
        vectors = await backend.embed(["hello", "world"])
        assert len(vectors) == 2
        assert all(len(v) == CANONICAL_DIM for v in vectors)
        norm = sum(x * x for x in vectors[0]) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-6)

    def test_space_tag_pins_model_and_stored_dim(self):
        backend = OllamaEmbedding("nomic-embed-text")
        assert backend.space == f"ollama-nomic-embed-text-{CANONICAL_DIM}"

    def test_space_tag_drops_version_suffix(self):
        # ":latest" and untagged are the same weights — must share a space.
        assert OllamaEmbedding("nomic-embed-text:latest").space == OllamaEmbedding("nomic-embed-text").space

    @pytest.mark.asyncio
    async def test_vector_count_mismatch_raises(self):
        backend = OllamaEmbedding(
            "nomic-embed-text", client=_client(lambda req: _embed_response(count=1, dim=768))
        )
        with pytest.raises(RuntimeError, match="1 vectors for 2 inputs"):
            await backend.embed(["a", "b"])

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        backend = OllamaEmbedding(
            "nomic-embed-text", client=_client(lambda req: httpx.Response(500))
        )
        with pytest.raises(httpx.HTTPStatusError):
            await backend.embed(["a"])


class TestAutoEmbedding:
    @pytest.mark.asyncio
    async def test_resolves_to_ollama_when_model_present(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                return _tags_response(["nomic-embed-text:latest", "llama3.2:3b"])
            if request.url.path == "/api/embed":
                return _embed_response(count=1, dim=768)
            raise AssertionError(f"unexpected path {request.url.path}")

        backend = AutoEmbedding("nomic-embed-text", client=_client(handler))
        [vector] = await backend.embed(["hello"])
        assert len(vector) == CANONICAL_DIM
        assert backend.space == f"ollama-nomic-embed-text-{CANONICAL_DIM}"

    @pytest.mark.asyncio
    async def test_falls_back_to_hash_when_model_missing(self, caplog):
        backend = AutoEmbedding(
            "nomic-embed-text", client=_client(lambda req: _tags_response(["llama3.2:3b"]))
        )
        with caplog.at_level("WARNING"):
            [vector] = await backend.embed(["hello"])
        assert backend.space == HashEmbedding.space
        assert len(vector) == CANONICAL_DIM
        assert any("hash embeddings" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_falls_back_to_hash_when_daemon_unreachable(self, caplog):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("daemon down", request=request)

        backend = AutoEmbedding("nomic-embed-text", client=_client(handler))
        with caplog.at_level("WARNING"):
            await backend.embed(["hello"])
        assert backend.space == HashEmbedding.space
        assert any("Ollama unreachable" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_probe_runs_once_and_delegate_is_cached(self):
        calls = {"tags": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tags":
                calls["tags"] += 1
                return _tags_response(["nomic-embed-text"])
            return _embed_response(count=1, dim=768)

        backend = AutoEmbedding("nomic-embed-text", client=_client(handler))
        await backend.embed(["one"])
        await backend.embed(["two"])
        assert calls["tags"] == 1

    def test_space_before_first_embed_raises(self):
        backend = AutoEmbedding("nomic-embed-text")
        with pytest.raises(RuntimeError, match="unresolved"):
            _ = backend.space

    @pytest.mark.asyncio
    async def test_hash_fallback_vectors_stay_in_hash_space(self):
        # Space-consistency contract: an auto backend that fell back to hash
        # produces vectors identical to a plain HashEmbedding (same space,
        # same values) — retrieval filtered by space keeps working.
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("daemon down", request=request)

        auto = AutoEmbedding("nomic-embed-text", client=_client(handler))
        [auto_vec] = await auto.embed(["same text"])
        [hash_vec] = await HashEmbedding().embed(["same text"])
        assert auto_vec == hash_vec


class TestFactory:
    def test_auto_backend_is_constructed(self):
        backend = build_embedding_backend("auto")
        assert isinstance(backend, AutoEmbedding)

    def test_auto_backend_honors_model_pin(self):
        backend = build_embedding_backend("auto", model="mxbai-embed-large")
        assert isinstance(backend, AutoEmbedding)

    def test_local_stays_default_hash(self):
        assert isinstance(build_embedding_backend("local"), HashEmbedding)

    def test_unknown_backend_rejected_with_full_choice_list(self):
        with pytest.raises(ValueError, match="'local', 'auto', or 'freellmpool'"):
            build_embedding_backend("banana")
