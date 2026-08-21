"""Scriptable in-memory adapter for unit tests and chaos simulation.

Each route carries a queue of behaviors consumed one per attempt
(a FailureKind to raise, or OK to succeed); an empty queue means success.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bebshax.llm.adapters.base import ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.types import LLMRequest, TokenUsage

OK = "ok"


@dataclass
class FakeRoute:
    candidate: RouteCandidate
    behaviors: list[FailureKind | str] = field(default_factory=list)
    reply: str = "fake reply"


class FakeAdapter(ProviderAdapter):
    def __init__(self, routes: list[FakeRoute]) -> None:
        self._routes = {(r.candidate.provider, r.candidate.model): r for r in routes}
        self._order = [r.candidate for r in routes]
        self.calls: list[str] = []

    async def candidates(self) -> list[RouteCandidate]:
        return list(self._order)

    async def complete(
        self, candidate: RouteCandidate, request: LLMRequest
    ) -> tuple[str, TokenUsage]:
        route = self._routes[(candidate.provider, candidate.model)]
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        behavior = route.behaviors.pop(0) if route.behaviors else OK
        if behavior != OK:
            raise AttemptFailed(
                FailureKind(behavior), candidate.provider, candidate.model, "scripted failure"
            )
        prompt_chars = sum(len(m.content) for m in request.messages)
        usage = TokenUsage(input_tokens=prompt_chars // 4, output_tokens=len(route.reply) // 4)
        return route.reply, usage
