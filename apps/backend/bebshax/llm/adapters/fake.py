"""Scriptable in-memory adapter for unit tests and chaos simulation.

Each route carries a queue of behaviors consumed one per attempt
(a FailureKind to raise, or OK to succeed); an empty queue means success.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate
from bebshax.llm.failures import AttemptFailed, FailureKind
from bebshax.llm.types import LLMRequest, TokenUsage

OK = "ok"


@dataclass
class FakeRoute:
    candidate: RouteCandidate
    behaviors: list[FailureKind | str] = field(default_factory=list)
    reply: str = "fake reply"
    replies: list[str] = field(default_factory=list)  # consumed per success; falls back to `reply`


class FakeAdapter(ProviderAdapter):
    def __init__(self, routes: list[FakeRoute]) -> None:
        self._routes = {(r.candidate.provider, r.candidate.model): r for r in routes}
        self._order = [r.candidate for r in routes]
        self.calls: list[str] = []
        self.requests: list[LLMRequest] = []

    async def candidates(self) -> list[RouteCandidate]:
        return list(self._order)

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        route = self._routes[(candidate.provider, candidate.model)]
        self.calls.append(f"{candidate.provider}/{candidate.model}")
        self.requests.append(request)
        behavior = route.behaviors.pop(0) if route.behaviors else OK
        if behavior != OK:
            raise AttemptFailed(
                FailureKind(behavior), candidate.provider, candidate.model, "scripted failure"
            )
        text = route.replies.pop(0) if route.replies else route.reply
        prompt_chars = sum(len(m.content) for m in request.messages)
        return AdapterCompletion(
            text=text,
            usage=TokenUsage(input_tokens=prompt_chars // 4, output_tokens=len(text) // 4),
            provider=candidate.provider,
            model=candidate.model,
        )
