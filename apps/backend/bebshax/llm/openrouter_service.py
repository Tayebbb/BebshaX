"""Central OpenRouter Service for BebshaX.

Provides:
- Role-based model configuration (MODEL_PERSONA, MODEL_REASONING, MODEL_EXTRACTION, MODEL_CRITIC)
- Network-free configuration report (GET health) and the live diagnostic probe (POST test)
- Safe error normalization

Completions are NOT offered here: every LLM call goes through LLMService (R3).
"""

from __future__ import annotations

import os
from typing import Optional

from bebshax.llm.adapters.openrouter_adapter import DEFAULT_MODELS, OpenRouterAdapter
from bebshax.llm.failures import LLMError
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.latency import DeadlineExpired, await_before, resolve_deadline
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType


class OpenRouterService:
    """Central manager for OpenRouter provider interactions."""

    def __init__(self, adapter: Optional[OpenRouterAdapter] = None) -> None:
        self._adapter = adapter or OpenRouterAdapter()

    @property
    def is_configured(self) -> bool:
        return bool(self._adapter.configuration_status()["configured"])

    def get_model_for_role(self, role: str) -> str:
        """Resolve the model name configured for a specific role or fallback to default."""
        role_env_map = {
            "persona": "MODEL_PERSONA",
            "reasoning": "MODEL_REASONING",
            "extraction": "MODEL_EXTRACTION",
            "critic": "MODEL_CRITIC",
            "browser": "MODEL_BROWSER",
        }
        env_var = role_env_map.get(role.lower())
        if env_var:
            configured = os.environ.get(env_var)
            if configured and configured.strip():
                return configured.strip()

        # Fallback to general OPENROUTER_MODEL or the first seed route
        return os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODELS[0]

    def configuration_report(self) -> dict:
        """Key configured? Which models? — answered WITHOUT any network call."""
        return self._adapter.configuration_status(model=self.get_model_for_role("reasoning"))

    async def health_check(self, model: Optional[str] = None, *, llm_service: LLMService) -> dict:
        """Run a governed diagnostic; configuration inspection itself never spends tokens."""
        configuration = self._adapter.configuration_status(model=model)
        if not configuration["configured"]:
            return configuration
        deadline = resolve_deadline(TaskType.EMERGENCY_FALLBACK)
        target_model = model or self.get_model_for_role("reasoning")
        try:
            candidates = await await_before(self._adapter.candidates(), deadline)
            models = [candidate.model for candidate in candidates]
            if model is None and target_model not in models and models:
                target_model = models[0]
            if target_model not in models:
                return {
                    "configured": True, "authenticated": False, "model": target_model,
                    "status": "error", "error_code": "OPENROUTER_MODEL_UNAVAILABLE",
                    "message": "Diagnostic model lacks current verified free catalogue metadata.",
                }
            result = await await_before(llm_service.complete(LLMRequest(
                task=TaskType.EMERGENCY_FALLBACK,
                messages=[ChatMessage(role="user", content='Return exactly the JSON object {"ok":true}.')],
                json_mode=True, max_output_tokens=64, temperature=0.0,
                preferred_provider="openrouter", preferred_model=target_model,
            )), deadline)
            if result.provider != "openrouter" or result.model == "unknown":
                return {
                    "configured": True, "authenticated": False, "status": "unverified",
                    "provider": result.provider, "model": result.model,
                    "request_id": result.provenance.request_id,
                    "message": "Governed routing completed without verifying an OpenRouter serving model.",
                }
            parsed = parse_llm_json(result.text)
            if not isinstance(parsed, dict) or parsed.get("ok") is not True:
                raise ValueError("invalid diagnostic object")
        except (LLMError, DeadlineExpired, ValueError):
            return {
                "configured": True, "authenticated": False, "model": target_model,
                "status": "error", "error_code": "OPENROUTER_DIAGNOSTIC_FAILED",
                "message": "Governed diagnostic did not produce a valid verified completion.",
            }
        return {
            "configured": True, "authenticated": True, "model": result.model,
            "provider": result.provider, "status": "healthy",
            "request_id": result.provenance.request_id,
            "latency_ms": result.provenance.total_latency_ms,
            "verified_response": result.text,
            "message": "OpenRouter verified through governed routing.",
        }

    async def aclose(self) -> None:
        await self._adapter.aclose()


# Shared singleton instance
_openrouter_service: Optional[OpenRouterService] = None


def get_openrouter_service() -> OpenRouterService:
    global _openrouter_service
    if _openrouter_service is None:
        _openrouter_service = OpenRouterService()
    return _openrouter_service
