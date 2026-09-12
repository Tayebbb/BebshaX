"""Govern fixed synthetic operations probes with an operator-supplied processing policy."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from bebshax.llm.governance import LLMRequestContext, RemoteProcessingPolicy, llm_request_context

if TYPE_CHECKING:
    from bebshax.llm.router import PoolRouter

ROOT = Path(__file__).resolve().parents[2]


def approved_synthetic_policy(environment: Mapping[str, str]) -> RemoteProcessingPolicy:
    try:
        policy = RemoteProcessingPolicy.model_validate_json(environment.get("BEBSHAX_REMOTE_PROCESSING_POLICY", "{}"))
    except ValidationError:
        raise ValueError("The explicit remote-processing policy is invalid") from None
    if not policy.synthetic_providers:
        raise ValueError("Synthetic remote processing is denied; provider keys and --allow-network are not approval")
    return policy


@asynccontextmanager
async def synthetic_probe_router(environment: Mapping[str, str] | None = None) -> AsyncIterator[PoolRouter]:
    environment = os.environ if environment is None else environment
    policy = approved_synthetic_policy(environment)
    from bebshax.llm.adapters.factory import build_default_adapters
    from bebshax.llm.router import PoolRouter

    provider_config = Path(environment.get("BEBSHAX_PROVIDER_CONFIG_PATH") or ROOT / "providers.toml")
    adapters = build_default_adapters(provider_config=provider_config)
    async with AsyncExitStack() as cleanup:
        for adapter in adapters.values():
            cleanup.push_async_callback(adapter.aclose)
        service = PoolRouter(adapters, processing_policy=policy)
        with llm_request_context(LLMRequestContext(data_classification="synthetic")):
            yield service