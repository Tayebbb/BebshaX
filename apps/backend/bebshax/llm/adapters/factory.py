"""Constructs the production adapter set. Lives inside adapters/ because
naming concrete adapters is an adapter-layer concern (RULES.md R1).
Keys must match the adapter names used in bebshax.llm.pools.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from bebshax.llm.adapters.base import ProviderAdapter
from bebshax.llm.adapters.embeddings import (
    EmbeddingBackend,
    FreellmpoolEmbedding,
    HashEmbedding,
)
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter
from bebshax.llm.adapters.openrouter_adapter import ANY_DATA_DENYING_UPSTREAM, OpenRouterAdapter
from bebshax.llm.adapters.provider_policy import approved_primary_providers, load_primary_catalog
from bebshax.llm.governance import RemoteProcessingPolicy

if TYPE_CHECKING:
    from bebshax.llm.quota import QuotaLedger

DEFAULT_POLICY_ID = "configured-providers-default"


def default_processing_policy(provider_config: Path) -> RemoteProcessingPolicy:
    """Approve exactly the providers the application catalog configures.

    Without an explicit BEBSHAX_REMOTE_PROCESSING_POLICY the router used to deny
    every remote destination, which with no local tier meant every AI feature
    failed while /api/health still reported ok. The reviewed catalog is the
    operator's configuration; OpenRouter is limited to upstreams that deny data
    collection until an explicit policy names them.
    """
    providers = frozenset(provider.id for provider in approved_primary_providers(load_primary_catalog(provider_config)))
    providers |= {"freellmpool", "openrouter"}
    return RemoteProcessingPolicy(
        policy_id=DEFAULT_POLICY_ID,
        synthetic_providers=providers, private_providers=providers,
        synthetic_openrouter_upstreams=frozenset({ANY_DATA_DENYING_UPSTREAM}),
        private_openrouter_upstreams=frozenset({ANY_DATA_DENYING_UPSTREAM}),
    )


def build_default_adapters(
    *, quota_ledger: QuotaLedger | None = None, provider_config: Path | None = None,
    initial_cooldowns: dict[tuple[str, str], float] | None = None,
    on_cooldown_change: Callable[[str, str, float], None] | None = None,
) -> dict[str, ProviderAdapter]:
    return {
        "freellmpool": FreellmpoolAdapter(
            routing="fast", quota_remaining=quota_ledger.remaining_fraction if quota_ledger is not None else None,
            provider_config=provider_config, initial_cooldowns=initial_cooldowns,
            on_cooldown_change=on_cooldown_change,
            reserve_attempt=quota_ledger.reserve_attempt if quota_ledger is not None else None,
        ),
        "openrouter": OpenRouterAdapter(
            discover_catalogue=True, reserve_attempt=quota_ledger.reserve_attempt if quota_ledger is not None else None,
        ),
    }


def build_embedding_backend(
    backend: str = "local", model: str | None = None, *, provider_config: Path | None = None,
    processing_policy: RemoteProcessingPolicy | None = None,
) -> EmbeddingBackend:
    if backend == "local":
        return HashEmbedding()
    if backend == "freellmpool":
        if not model:
            raise ValueError("BEBSHAX_EMBEDDING_MODEL must be set for the freellmpool backend")
        return FreellmpoolEmbedding(model=model, provider_config=provider_config, processing_policy=processing_policy)
    raise ValueError(
        f"unknown embedding backend '{backend}' (expected 'local' or 'freellmpool')"
    )

