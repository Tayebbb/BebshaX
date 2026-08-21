from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from bebshax.llm.types import LLMRequest, TokenUsage


class RouteCandidate(BaseModel):
    provider: str
    model: str
    context_window: int = 128_000
    supports_json: bool = True
    supports_tools: bool = False


class ProviderAdapter(ABC):
    """Boundary contract between BebshaX and any LLM backend."""

    @abstractmethod
    async def candidates(self) -> list[RouteCandidate]:
        """Currently available routes, in the adapter's preference order."""

    @abstractmethod
    async def complete(
        self, candidate: RouteCandidate, request: LLMRequest
    ) -> tuple[str, TokenUsage]:
        """Return (text, usage) or raise AttemptFailed with a classified kind."""
