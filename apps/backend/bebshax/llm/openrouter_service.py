"""Central OpenRouter Service for BebshaX.

Provides:
- Role-based model configuration (MODEL_PERSONA, MODEL_REASONING, MODEL_EXTRACTION, MODEL_CRITIC)
- Health check execution and diagnostics
- Structured JSON generation
- Safe error normalization
"""

from __future__ import annotations

import os
from typing import Optional

from bebshax.llm.adapters.openrouter_adapter import OpenRouterAdapter
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType


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

        # Fallback to general OPENROUTER_MODEL or default
        return (
            os.environ.get("OPENROUTER_MODEL")
            or "meta-llama/llama-3.3-70b-instruct:free"
        )

    async def health_check(self, model: Optional[str] = None) -> dict:
        """Execute a safe, authenticated diagnostic health check."""
        target_model = model or self.get_model_for_role("reasoning")
        return await self._adapter.health_check(model=target_model)

    async def generate_structured(
        self,
        messages: list[ChatMessage],
        role: str = "persona",
        temperature: float = 0.7,
        max_tokens: Optional[int] = 2048,
    ) -> dict:
        """Generate structured response using the designated model role."""
        model = self.get_model_for_role(role)
        req = LLMRequest(
            task=TaskType.PERSONA_GENERATION,
            messages=messages,
            json_mode=True,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        candidates = await self._adapter.candidates()
        target_candidate = next((c for c in candidates if c.model == model), None)
        if not target_candidate:
            from bebshax.llm.adapters.base import RouteCandidate

            target_candidate = RouteCandidate(
                provider="openrouter",
                model=model,
                context_window=128_000,
                supports_json=True,
            )

        completion = await self._adapter.complete(target_candidate, req)
        import json

        text = completion.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
        return {
            "data": json.loads(text),
            "model_used": completion.model,
            "usage": {
                "input_tokens": completion.usage.input_tokens,
                "output_tokens": completion.usage.output_tokens,
            },
        }


# Shared singleton instance
_openrouter_service: Optional[OpenRouterService] = None


def get_openrouter_service() -> OpenRouterService:
    global _openrouter_service
    if _openrouter_service is None:
        _openrouter_service = OpenRouterService()
    return _openrouter_service
