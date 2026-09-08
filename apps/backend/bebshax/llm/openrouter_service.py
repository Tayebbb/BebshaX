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


class OpenRouterService:
    """Central manager for OpenRouter provider interactions."""

    def __init__(self, adapter: Optional[OpenRouterAdapter] = None) -> None:
        self._adapter = adapter or OpenRouterAdapter()

    @property
    def is_configured(self) -> bool:
        key = os.environ.get("OPENROUTER_API_KEY")
        return bool(key and key.strip())

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

    async def health_check(self, model: Optional[str] = None) -> dict:
        """Execute a safe, authenticated diagnostic health check (spends one real call)."""
        target_model = model or self.get_model_for_role("reasoning")
        return await self._adapter.health_check(model=target_model)


# Shared singleton instance
_openrouter_service: Optional[OpenRouterService] = None


def get_openrouter_service() -> OpenRouterService:
    global _openrouter_service
    if _openrouter_service is None:
        _openrouter_service = OpenRouterService()
    return _openrouter_service
