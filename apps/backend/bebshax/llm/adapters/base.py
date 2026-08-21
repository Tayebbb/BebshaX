from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from bebshax.llm.types import LLMRequest, TokenUsage


class RouteCandidate(BaseModel):
    provider: str
    model: str
    context_window: int = 128_000
    supports_json: bool = True
    supports_tools: bool = False


class AdapterCompletion(BaseModel):
    """Adapter result. provider/model are the CONCRETE serving route — an
    aggregating adapter (freellmpool) resolves virtual candidates like 'auto'
    to the real provider/model so provenance stays truthful."""

    text: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provider: str
    model: str
    notes: list[str] = Field(default_factory=list)  # e.g. internal failover info


class ProviderAdapter(ABC):
    """Boundary contract between BebshaX and any LLM backend."""

    @abstractmethod
    async def candidates(self) -> list[RouteCandidate]:
        """Currently available routes, in the adapter's preference order."""

    @abstractmethod
    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        """Return a completion or raise AttemptFailed with a classified kind."""
