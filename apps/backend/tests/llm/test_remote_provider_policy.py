from dataclasses import replace

import pytest
from freellmpool.models import Model, Provider

from bebshax.llm.adapters.provider_policy import approved_primary_providers


def remote_provider(**changes) -> Provider:
    provider = Provider(
        id="catalog-added-provider",
        label="Catalog provider",
        adapter="openai",
        base_url="https://inference.example.com/v1",
        auth="none",
        models=(Model(name="full-context-model", context=131072),),
    )
    return replace(provider, **changes)


def test_primary_names_come_from_catalog_not_a_fixed_allowlist() -> None:
    provider = remote_provider()
    assert approved_primary_providers([provider]) == [provider]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "ollama"},
        {"id": "openrouter"},
        {"base_url": "https://ollama.com/v1"},
        {"base_url": "https://api.ollama.com/v1"},
        {"base_url": "https://openrouter.ai/api/v1"},
        {"key_env": "OPENROUTER_API_KEY"},
        {"key_env": "OLLAMA_API_KEY"},
        {"base_url": "http://localhost:11434/v1"},
        {"base_url": "https://127.0.0.1/v1"},
        {"base_url": "https://[::1]/v1"},
        {"base_url": "https://10.0.0.1/v1"},
        {"base_url": "https://localhost./v1"},
        {"base_url": "https://2130706433/v1"},
        {"base_url": "https://server.internal/v1"},
        {"base_url": "https://user:password@inference.example.com/v1"},
        {"adapter": "unreviewed-plugin"},
        {"models": (Model(name="openrouter/free", context=131072),)},
        {"models": (Model(name="retired", enabled=False, context=131072),)},
    ],
)
def test_legacy_provider_configuration_cannot_restore_excluded_routes(changes) -> None:
    assert approved_primary_providers([remote_provider(**changes)]) == []


def test_excluded_models_do_not_remove_other_approved_models() -> None:
    good_model = Model(name="verified-free-model", context=131072)
    provider = remote_provider(models=(Model(name="openrouter/free"), good_model))
    [approved] = approved_primary_providers([provider])
    assert approved.models == (good_model,)


def test_empty_catalog_stays_empty() -> None:
    assert approved_primary_providers([]) == []