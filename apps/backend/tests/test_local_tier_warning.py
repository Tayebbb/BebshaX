"""Retired local-tier startup paths cannot return as implicit fallback probes."""

import importlib
import os

from bebshax import main
from bebshax.config import Settings
from bebshax.llm.pools import POOLS


def test_local_tier_startup_probe_is_removed():
    assert not hasattr(main, "warn_if_local_tier_down")


def test_every_pool_has_only_primary_and_secondary_remote_adapters():
    assert all(list(pool.adapters) == ["freellmpool", "openrouter"] for pool in POOLS.values())


def test_local_hash_embedding_is_still_supported():
    assert Settings(_env_file=None).embedding_backend == "local"


def test_import_does_not_mutate_provider_config_environment(monkeypatch):
    monkeypatch.delenv("FREELLMPOOL_CONFIG", raising=False)
    importlib.reload(main)
    assert "FREELLMPOOL_CONFIG" not in os.environ
