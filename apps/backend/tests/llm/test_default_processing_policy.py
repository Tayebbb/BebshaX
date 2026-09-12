"""The out-of-the-box AI path: derived processing policy, .env credential bridge,
OpenRouter upstream sentinel and diagnosable empty-candidate routing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bebshax.config import export_provider_credentials
from bebshax.llm import ChatMessage, LLMRequest, PoolRouter, TaskType
from bebshax.llm.adapters.factory import DEFAULT_POLICY_ID, default_processing_policy
from bebshax.llm.adapters.fake import FakeAdapter
from bebshax.llm.adapters.openrouter_adapter import ANY_DATA_DENYING_UPSTREAM, OpenRouterAdapter
from bebshax.llm.failures import AllCandidatesFailed
from bebshax.llm.governance import DispatchApproval, LLMRequestContext, RemoteProcessingPolicy, governed_operation, llm_request_context

PROVIDERS_TOML = Path(__file__).resolve().parents[4] / "providers.toml"


class RemoteFakeAdapter(FakeAdapter):
    remote_processing = True


def test_default_policy_approves_the_reviewed_catalog_for_both_classifications() -> None:
    policy = default_processing_policy(PROVIDERS_TOML)
    assert policy.policy_id == DEFAULT_POLICY_ID
    assert {"freellmpool", "openrouter", "pollinations", "ovh", "llm7", "kilo"} <= set(policy.private_providers)
    assert policy.private_providers == policy.synthetic_providers
    assert policy.allowed_openrouter_upstreams("private") == (ANY_DATA_DENYING_UPSTREAM,)
    # Retired tiers never re-enter through the derived default.
    assert "ollama" not in policy.private_providers


def test_default_policy_is_a_valid_explicit_policy_round_trip() -> None:
    policy = default_processing_policy(PROVIDERS_TOML)
    assert RemoteProcessingPolicy.model_validate_json(policy.model_dump_json()) == policy


async def test_openrouter_sentinel_relies_on_data_collection_deny_instead_of_a_host_allowlist() -> None:
    adapter = OpenRouterAdapter(discover_catalogue=False)

    async def preferences() -> dict:
        return adapter._provider_preferences()

    wildcard = await governed_operation(preferences(), ("openrouter",), (ANY_DATA_DENYING_UPSTREAM,))
    assert wildcard["data_collection"] == "deny"
    assert wildcard["max_price"] == {"prompt": 0, "completion": 0}
    assert "only" not in wildcard and "allow_fallbacks" not in wildcard

    explicit = await governed_operation(preferences(), ("openrouter",), ("Chutes",))
    assert explicit["only"] == ["Chutes"] and explicit["allow_fallbacks"] is False


def test_dispatch_approval_carries_the_sentinel_verbatim() -> None:
    assert DispatchApproval(("openrouter",), (ANY_DATA_DENYING_UPSTREAM,)).openrouter_upstreams == ("*",)


async def test_empty_candidate_discovery_is_recorded_in_the_routing_path() -> None:
    records = []
    router = PoolRouter(
        {"freellmpool": RemoteFakeAdapter([]), "openrouter": RemoteFakeAdapter([])},
        on_provenance=records.append, processing_policy=RemoteProcessingPolicy(policy_id="deny-everything"),
    )
    context = LLMRequestContext(owner_user_id="owner-a", data_classification="private")
    with llm_request_context(context), pytest.raises(AllCandidatesFailed) as failure:
        await router.complete(LLMRequest(
            task=TaskType.PERSONA_RESPONSE, messages=[ChatMessage(role="user", content="hello")], json_mode=True,
        ))
    notes = [step for step in failure.value.provenance.routing_path if "no eligible candidates" in step]
    assert notes, failure.value.provenance.routing_path
    assert all("policy deny-everything approves: none" in step and "classification=private" in step for step in notes)
    assert failure.value.provenance.attempts == []


def test_export_provider_credentials_bridges_only_provider_names_and_never_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BEBSHAX_JWT_SECRET=never-exported\nVITE_API_BASE=http://frontend\n"
        "OPENROUTER_API_KEY=sk-from-dotenv\nGROQ_API_KEY=gsk-from-dotenv\nEMPTY_KEY=\n",
        encoding="utf-8",
    )
    for name in ("BEBSHAX_JWT_SECRET", "VITE_API_BASE", "OPENROUTER_API_KEY", "EMPTY_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk-from-process")

    exported = export_provider_credentials(env_file)

    assert sorted(exported) == ["EMPTY_KEY", "OPENROUTER_API_KEY"]
    assert os.environ["OPENROUTER_API_KEY"] == "sk-from-dotenv"
    assert os.environ["GROQ_API_KEY"] == "gsk-from-process"
    assert "BEBSHAX_JWT_SECRET" not in os.environ and "VITE_API_BASE" not in os.environ


def test_export_provider_credentials_without_env_file_is_a_noop(tmp_path: Path) -> None:
    assert export_provider_credentials(tmp_path / "missing.env") == []
