"""Historical judge-disjointness helpers; the local benchmark CLI is retired."""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit("This historical benchmark is retired. Use scripts/release_preflight.py for current operations checks.")

import json
import re
from collections.abc import Callable
from bebshax.llm import SingleAdapterLLMService
from bebshax.llm.adapters.base import (
    AdapterCompletion,
    ProviderAdapter,
    RouteCandidate,
)
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

RUBRIC = {
    "persona_consistency": 0.25,
    "naturalness": 0.20,
    "instruction_following": 0.15,
    "context_memory": 0.15,
    "specificity": 0.15,
    "response_stability": 0.10,
}


def _weights(route: str) -> str:
    """Model identity independent of gateway: 'ovh/Meta-Llama-3.3-70B' and
    'openrouter/meta-llama/llama-3.3-70b-instruct:free' compare on the model
    token only, lower-cased, without ':free'/':latest' tags."""
    model = route.rsplit("/", 1)[-1].lower()
    return model.split(":", 1)[0]


def shares_weights(judge_route: str, arm_routes: set[str]) -> bool:
    """True when the judge is the same route OR the same model weights as any arm."""
    return judge_route in arm_routes or _weights(judge_route) in {_weights(r) for r in arm_routes}


class ExcludeArmRoutes(ProviderAdapter):
    """Drop candidate routes that served an arm (exact or same weights). Adapters
    that resolve a virtual route internally (freellmpool) are re-checked after
    the call — see `judge_disjoint`."""

    def __init__(self, inner: ProviderAdapter, arm_routes: set[str]) -> None:
        self._inner = inner
        self._arm_routes = arm_routes
        self.remote_processing = inner.remote_processing

    async def candidates(self) -> list[RouteCandidate]:
        return [
            c
            for c in await self._inner.candidates()
            if c.model == "auto" or not shares_weights(f"{c.provider}/{c.model}", self._arm_routes)
        ]

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        return await self._inner.complete(candidate, request)


def transcript_text(run: dict) -> str:
    return "\n\n".join(f"Q: {t['question']}\nA: {t['reply']}" for t in run["turns"])


async def judge(judge_llm, run_a: dict, run_b: dict) -> dict:
    dims = ", ".join(f'"{k}"' for k in RUBRIC)
    prompt = (
        "You are a strict qualitative-research QA judge. Two interviews used the SAME persona spec "
        "(Farhana Kabir, 31, accountant in Gulshan, street lunch 100-150 BDT/day, skeptical of "
        "subscriptions, bKash user) and the SAME questions. Score EACH transcript 0-10 per dimension: "
        f"{dims}.\n"
        "persona_consistency: stays in character, facts match the spec and earlier answers.\n"
        "naturalness: sounds like a real person, not an AI assistant.\n"
        "instruction_following: answers the question asked, first person, no meta talk.\n"
        "context_memory: turn 4 must reference the price given in turn 1 consistently.\n"
        "specificity: concrete numbers/places/habits, no generic filler.\n"
        "response_stability: no format breakage, no contradictions between turns.\n"
        'Return ONLY JSON: {"A": {<dim>: <0-10>, ...}, "B": {...}, "notes": "<2 sentences>"}\n\n'
        f"=== TRANSCRIPT A ===\n{transcript_text(run_a)}\n\n=== TRANSCRIPT B ===\n{transcript_text(run_b)}"
    )
    res = await judge_llm.complete(
        LLMRequest(
            task=TaskType.STRUCTURED_OUTPUT,
            messages=[ChatMessage(role="user", content=prompt)],
            json_mode=True,
            temperature=0.1,
            max_output_tokens=800,
        )
    )
    cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", res.text.strip())
    return {"scores": json.loads(cleaned), "judge_route": f"{res.provider}/{res.model}"}


def weighted(scores: dict) -> float:
    return round(sum(float(scores[d]) * w for d, w in RUBRIC.items()), 2)


class JudgeNotDisjoint(RuntimeError):
    """No judge route disjoint from every arm's serving route could be obtained."""


async def judge_disjoint(
    run_a: dict,
    run_b: dict,
    arm_routes: set[str],
    judge_adapters: list[tuple[str, Callable[[], ProviderAdapter]]] | None = None,
) -> dict:
    """Judge with a route that is NOT any arm's serving route (nor the same
    weights behind another gateway). LLM-as-judge self-preference is a known
    bias, so this is a hard requirement: candidates are tried in order and a
    verdict whose served route collides with an arm is DISCARDED; when every
    candidate collides or fails, raise instead of quietly judging with arm B."""
    if judge_adapters is None:
        raise JudgeNotDisjoint("The retired benchmark requires explicitly injected approved judge adapters")
    rejected: list[str] = []
    for label, build in judge_adapters:
        adapter = build()
        try:
            verdict = await judge(SingleAdapterLLMService(ExcludeArmRoutes(adapter, arm_routes)), run_a, run_b)
        except Exception as exc:  # noqa: BLE001 — any adapter/JSON failure just disqualifies this judge
            rejected.append(f"{label}: unavailable ({exc!r})")
            continue
        finally:
            await adapter.aclose()
        if shares_weights(verdict["judge_route"], arm_routes):
            rejected.append(f"{label}: served by {verdict['judge_route']} which is an arm's route/weights")
            continue
        verdict["rejected_judges"] = rejected
        return verdict
    raise JudgeNotDisjoint(
        "no judge route disjoint from the arms' serving routes "
        f"{sorted(arm_routes)}; tried: {rejected}"
    )
