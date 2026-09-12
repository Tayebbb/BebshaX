from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from pydantic import BaseModel, Field

from bebshax.llm.provenance import ProviderObservation
from bebshax.llm.types import LLMRequest, TokenUsage


class RouteCandidate(BaseModel):
    provider: str
    model: str
    context_window: int = 128_000
    supports_json: bool = True
    supports_tools: bool = False
    supported_parameters: list[str] | None = None
    max_output_tokens: int | None = None


class AdapterCompletion(BaseModel):
    """Adapter result. provider/model are the CONCRETE serving route — an
    aggregating adapter (freellmpool) resolves virtual candidates like 'auto'
    to the real provider/model so provenance stays truthful."""

    text: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provider: str
    model: str
    notes: list[str] = Field(default_factory=list)  # e.g. internal failover info
    cached: bool = False
    latency_ms: float | None = None
    finish_reason: str | None = None
    observations: list[ProviderObservation] = Field(default_factory=list)


class StreamDelta(BaseModel):
    """Incremental text chunk of an in-flight completion."""

    text: str


class StreamDone(BaseModel):
    """Terminal stream event carrying the full, canonical completion."""

    completion: AdapterCompletion


StreamEvent = StreamDelta | StreamDone


class ProviderAdapter(ABC):
    """Boundary contract between BebshaX and any LLM backend."""

    manages_cooldowns: bool = False
    remote_processing: bool = True

    @abstractmethod
    async def candidates(self) -> list[RouteCandidate]:
        """Currently available routes, in the adapter's preference order."""

    async def candidates_for(self, request: LLMRequest) -> list[RouteCandidate]:
        """Request-aware discovery; existing adapters retain their candidate contract."""
        return await self.candidates()

    @abstractmethod
    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        """Return a completion or raise AttemptFailed with a classified kind."""

    async def stream(
        self, candidate: RouteCandidate, request: LLMRequest
    ) -> AsyncGenerator[StreamEvent, None]:
        """Yield StreamDelta chunks then a final StreamDone.

        Default: adapters without native streaming resolve the full completion
        and emit it as ONE delta — callers get identical text/provenance, just
        without incremental rendering. Raises AttemptFailed like complete().
        """
        completion = await self.complete(candidate, request)
        yield StreamDelta(text=completion.text)
        yield StreamDone(completion=completion)

    async def aclose(self) -> None:
        """Release adapter resources; default no-op."""
        return None
