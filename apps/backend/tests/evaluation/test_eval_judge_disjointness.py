"""scripts/judge_local_interview.py: the LLM judge must be disjoint from every
arm's serving route (and weights) — it used to fall back to the arm-B service,
so 2 of 3 historic gate runs were scored by the model under test."""

from __future__ import annotations

import json

import pytest

from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import FailureKind
from scripts.judge_local_interview import (
    ExcludeArmRoutes,
    JudgeNotDisjoint,
    judge_disjoint,
    shares_weights,
)

ARM_ROUTES = {"ollama/llama3.2:3b", "llm7/codestral-latest"}
_SCORES = json.dumps({
    "A": {k: 8 for k in ("persona_consistency", "naturalness", "instruction_following", "context_memory", "specificity", "response_stability")},
    "B": {k: 7 for k in ("persona_consistency", "naturalness", "instruction_following", "context_memory", "specificity", "response_stability")},
    "notes": "scripted",
})
_RUN = {"turns": [{"question": "q", "reply": "a", "served_by": "llm7/codestral-latest", "latency_ms": 1}]}


def test_shares_weights_matches_exact_routes_and_same_model_behind_another_gateway():
    assert shares_weights("llm7/codestral-latest", ARM_ROUTES) is True
    assert shares_weights("openrouter/mistralai/codestral-latest", ARM_ROUTES) is True  # same weights
    assert shares_weights("ovh/llama3.2:3b", ARM_ROUTES) is True
    assert shares_weights("groq/llama-3.1-8b-instant", ARM_ROUTES) is False
    assert shares_weights("openrouter/qwen/qwen-2.5-72b-instruct:free", ARM_ROUTES) is False


async def test_exclude_arm_routes_filters_candidates_but_keeps_virtual_auto():
    inner = FakeAdapter([
        FakeRoute(RouteCandidate(provider="llm7", model="codestral-latest")),
        FakeRoute(RouteCandidate(provider="groq", model="llama-3.1-8b-instant")),
        FakeRoute(RouteCandidate(provider="freellmpool", model="auto")),
    ])
    remaining = await ExcludeArmRoutes(inner, ARM_ROUTES).candidates()
    assert [f"{c.provider}/{c.model}" for c in remaining] == ["groq/llama-3.1-8b-instant", "freellmpool/auto"]


async def test_judge_disjoint_discards_a_verdict_served_by_an_arm_route():
    class ServedByArm(FakeAdapter):
        """Virtual 'auto' passes the candidate filter; the concrete serving
        route only becomes known after the call — the post-check must catch it."""

        async def complete(self, candidate, request):
            completion = await super().complete(candidate, request)
            return completion.model_copy(update={"provider": "llm7", "model": "codestral-latest"})

    colliding = ServedByArm([FakeRoute(RouteCandidate(provider="freellmpool", model="auto"), reply=_SCORES)])
    disjoint = FakeAdapter([FakeRoute(RouteCandidate(provider="groq", model="llama-3.1-8b-instant"), reply=_SCORES)])
    verdict = await judge_disjoint(
        _RUN, _RUN, set(ARM_ROUTES),
        judge_adapters=[("colliding", lambda: colliding), ("disjoint", lambda: disjoint)],
    )
    assert verdict["judge_route"] == "groq/llama-3.1-8b-instant"
    assert verdict["scores"]["A"]["naturalness"] == 8
    assert any("llm7/codestral-latest" in r for r in verdict["rejected_judges"])


async def test_judge_disjoint_fails_loudly_when_no_disjoint_judge_exists():
    only_arm = FakeAdapter([FakeRoute(RouteCandidate(provider="llm7", model="codestral-latest"), reply=_SCORES)])
    down = FakeAdapter([FakeRoute(RouteCandidate(provider="groq", model="x"), behaviors=[FailureKind.TIMEOUT])])
    with pytest.raises(JudgeNotDisjoint) as excinfo:
        await judge_disjoint(
            _RUN, _RUN, set(ARM_ROUTES),
            judge_adapters=[("only_arm", lambda: only_arm), ("down", lambda: down)],
        )
    message = str(excinfo.value)
    assert "disjoint" in message and "only_arm" in message and "down" in message
