"""Constructs the production adapter set. Lives inside adapters/ because
naming concrete adapters is an adapter-layer concern (RULES.md R1).
Keys must match the adapter names used in bebshax.llm.pools.
"""

from bebshax.llm.adapters.base import ProviderAdapter
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter


def build_default_adapters() -> dict[str, ProviderAdapter]:
    return {"freellmpool": FreellmpoolAdapter(), "ollama": OllamaAdapter()}
