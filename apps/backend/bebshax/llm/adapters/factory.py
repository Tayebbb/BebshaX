"""Constructs the production adapter set. Lives inside adapters/ because
naming concrete adapters is an adapter-layer concern (RULES.md R1).
Keys must match the adapter names used in bebshax.llm.pools.
"""

from bebshax.llm.adapters.base import ProviderAdapter
from bebshax.llm.adapters.embeddings import (
    DEFAULT_OLLAMA_EMBED_MODEL,
    AutoEmbedding,
    EmbeddingBackend,
    FreellmpoolEmbedding,
    HashEmbedding,
)
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter
from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter


def build_default_adapters() -> dict[str, ProviderAdapter]:
    return {
        # Primary: OpenRouter (direct). Free routes are discovered from the live
        # catalogue at first use — the static seed list drifts to 404s.
        "openrouter": OpenRouterAdapter(discover_catalogue=True),
        # "fast" = freellmpool's smoothed-latency-first ranking; the default
        # "fair" spreads by least-used and keeps picking measured-slow targets.
        "freellmpool": FreellmpoolAdapter(routing="fast"),
        "ollama": OllamaAdapter(),  # Tertiary: local Ollama fallback
    }


def build_embedding_backend(backend: str = "local", model: str | None = None) -> EmbeddingBackend:
    if backend == "local":
        return HashEmbedding()
    if backend == "auto":
        # Lazily probes Ollama on first embed; falls back to the hash backend
        # with one warning naming the space in use (see AutoEmbedding).
        return AutoEmbedding(model=model or DEFAULT_OLLAMA_EMBED_MODEL)
    if backend == "freellmpool":
        if not model:
            raise ValueError("BEBSHAX_EMBEDDING_MODEL must be set for the freellmpool backend")
        return FreellmpoolEmbedding(model=model)
    raise ValueError(
        f"unknown embedding backend '{backend}' (expected 'local', 'auto', or 'freellmpool')"
    )

