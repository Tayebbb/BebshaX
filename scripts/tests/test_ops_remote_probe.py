import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bebshax.llm.governance import LLMRequestContext, get_llm_request_context, llm_request_context
from scripts.ops.remote_probe import ROOT, approved_synthetic_policy, synthetic_probe_router


class RemoteProbePolicyTests(unittest.IsolatedAsyncioTestCase):
    def configuration(self) -> dict[str, str]:
        return {"BEBSHAX_REMOTE_PROCESSING_POLICY": json.dumps({
            "policy_id": "synthetic-test-fixture", "synthetic_providers": ["fixture-provider"],
        })}

    async def test_missing_policy_keys_only_and_private_only_approval_fail_before_adapter_construction(self) -> None:
        for environment in ({}, {"OPENROUTER_API_KEY": "synthetic-sentinel"},
                            {"BEBSHAX_REMOTE_PROCESSING_POLICY": '{"private_providers":["fixture-provider"]}'}):
            with self.subTest(kind=list(environment)), patch("bebshax.llm.adapters.factory.build_default_adapters") as build:
                with self.assertRaises(ValueError):
                    async with synthetic_probe_router(environment):
                        self.fail("Unapproved remote probe was admitted")
                build.assert_not_called()

    def test_invalid_or_unknown_policy_input_fails_without_echoing_values(self) -> None:
        for policy in ("", "not-json-synthetic-sentinel", '{"unknown":"synthetic-sentinel"}', "[]"):
            with self.subTest(policy=policy[:1]), self.assertRaisesRegex(ValueError, "^The explicit remote-processing policy is invalid$"):
                approved_synthetic_policy({"BEBSHAX_REMOTE_PROCESSING_POLICY": policy})

    async def test_explicit_policy_is_forwarded_unchanged_and_synthetic_context_is_scoped(self) -> None:
        adapters = {name: SimpleNamespace(aclose=AsyncMock()) for name in ("freellmpool", "openrouter")}
        outer = LLMRequestContext(owner_user_id="private-owner-fixture", data_classification="private")
        with patch("bebshax.llm.adapters.factory.build_default_adapters", return_value=adapters) as build, \
                patch("bebshax.llm.router.PoolRouter") as router, llm_request_context(outer):
            async with synthetic_probe_router(self.configuration()) as service:
                self.assertIs(service, router.return_value)
                self.assertEqual(get_llm_request_context().data_classification, "synthetic")
                self.assertIsNone(get_llm_request_context().owner_user_id)
                policy = router.call_args.kwargs["processing_policy"]
                self.assertEqual(policy.policy_id, "synthetic-test-fixture")
                self.assertEqual(policy.synthetic_providers, frozenset({"fixture-provider"}))
                self.assertEqual(policy.private_providers, frozenset())
                self.assertEqual(policy.synthetic_openrouter_upstreams, frozenset())
                self.assertEqual(policy.private_openrouter_upstreams, frozenset())
            self.assertIs(get_llm_request_context(), outer)
            build.assert_called_once_with(provider_config=ROOT / "providers.toml")
        for adapter in adapters.values():
            adapter.aclose.assert_awaited_once()

    async def test_all_adapters_close_when_router_initialization_fails(self) -> None:
        adapters = {name: SimpleNamespace(aclose=AsyncMock()) for name in ("freellmpool", "openrouter")}
        with patch("bebshax.llm.adapters.factory.build_default_adapters", return_value=adapters), \
                patch("bebshax.llm.router.PoolRouter", side_effect=ValueError("synthetic-init-failure")), \
                self.assertRaises(ValueError):
            async with synthetic_probe_router(self.configuration()):
                self.fail("Invalid router was admitted")
        for adapter in adapters.values():
            adapter.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()