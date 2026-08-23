"""Constructs the production adapter set. Lives inside adapters/ because
naming concrete adapters is an adapter-layer concern (RULES.md R1).
Keys must match the adapter names used in bebshax.llm.pools.
"""

from bebshax.llm.adapters.base import ProviderAdapter
from bebshax.llm.adapters.embeddings import EmbeddingBackend, FreellmpoolEmbedding, HashEmbedding
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter


def build_default_adapters() -> dict[str, ProviderAdapter]:
    return {"freellmpool": FreellmpoolAdapter(), "ollama": OllamaAdapter()}


def build_embedding_backend(backend: str = "local", model: str | None = None) -> EmbeddingBackend:
    if backend == "local":
        return HashEmbedding()
    if backend == "freellmpool":
        if not model:
            raise ValueError("BEBSHAX_EMBEDDING_MODEL must be set for the freellmpool backend")
        return FreellmpoolEmbedding(model=model)
    raise ValueError(f"unknown embedding backend '{backend}' (expected 'local' or 'freellmpool')")
