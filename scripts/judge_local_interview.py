"""Judged side-by-side: local llama3.2:3b vs the current best free-pool route.

Same persona + same 5-question interview script through the REAL InterviewEngine,
then a blind LLM judge scores both transcripts on the owner's weighted rubric
(persona consistency 25%, naturalness 20%, instruction following 15%,
context/memory 15%, specificity 15%, stability 10%). Production bar: 8/10.

Output: data/metadata/local_3b_gate_<ts>.json + console summary. Nothing is
fabricated — raw judge output and full transcripts are persisted.

Run:  .venv\\Scripts\\python scripts/judge_local_interview.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.environ.setdefault("BEBSHAX_JWT_SECRET", "x" * 40)  # config import guard for scripts
os.environ.setdefault("FREELLMPOOL_CONFIG", str(REPO / "providers.toml"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import bebshax.interview.orm  # noqa: F401, E402
import bebshax.memory.orm  # noqa: F401, E402
import bebshax.persona.orm  # noqa: F401, E402
from bebshax.db.models import Base  # noqa: E402
from bebshax.llm import SingleAdapterLLMService  # noqa: E402
from bebshax.llm.adapters.base import AdapterCompletion, ProviderAdapter, RouteCandidate  # noqa: E402
from bebshax.llm.adapters.embeddings import HashEmbedding  # noqa: E402
from bebshax.llm.adapters.freellmpool_adapter import FreellmpoolAdapter  # noqa: E402
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter  # noqa: E402
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType  # noqa: E402
from bebshax.interview.engine import InterviewEngine  # noqa: E402
from bebshax.memory.service import MemoryService  # noqa: E402
from bebshax.persona.schema import PersonaAttribute, PersonaProfile  # noqa: E402
from bebshax.persona.store import create_business, save_persona  # noqa: E402

LOCAL_MODEL = "llama3.2:3b"
QUESTIONS = [
    "Walk me through what you ate for lunch yesterday — where did it come from and what did it cost?",
    "What is the most frustrating part of how you handle lunch on workdays?",
    "Would you pay 3000 BDT per month for healthy delivered lunches? Why or why not?",
    "Earlier you told me what lunch costs you — how does that compare over a month?",
    "What would make you cancel such a subscription after the first month?",
]

RUBRIC = {
    "persona_consistency": 0.25,
    "naturalness": 0.20,
    "instruction_following": 0.15,
    "context_memory": 0.15,
    "specificity": 0.15,
    "response_stability": 0.10,
}


class PinnedModel(ProviderAdapter):
    """Restrict an adapter to routes whose model name contains `needle`."""

    def __init__(self, inner: ProviderAdapter, needle: str) -> None:
        self._inner = inner
        self._needle = needle

    async def candidates(self) -> list[RouteCandidate]:
        return [c for c in await self._inner.candidates() if self._needle in c.model]

    async def complete(self, candidate: RouteCandidate, request: LLMRequest) -> AdapterCompletion:
        return await self._inner.complete(candidate, request)


def _persona() -> PersonaProfile:
    return PersonaProfile(
        business_id="",  # filled after create_business
        name="Farhana Kabir",
        age=31,
        occupation="Senior Accountant at a Gulshan trading firm",
        location="Gulshan, Dhaka, Bangladesh",
        income_range="65,000-80,000 BDT/month",
        education="MBA (Finance)",
        description=(
            "Works 9-10 hour days; buys street lunch (100-150 BDT/day) near the office "
            "most workdays; tired of oily food and afternoon energy crashes; careful with "
            "money and skeptical of subscriptions; pays with bKash."
        ),
        attributes=[
            PersonaAttribute(key="pain_point", value="oily street lunch causes 3pm energy crash"),
            PersonaAttribute(key="budget", value="lunch spend 100-150 BDT/day (~2,500-3,600/month)"),
            PersonaAttribute(key="constraint", value="cancels any service that fails twice in a week"),
            PersonaAttribute(key="preference", value="Bengali home-style food over fast food"),
        ],
    )


async def run_interview(llm, tag: str) -> dict:
    engine_db = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine_db.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = sessionmaker(engine_db, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        business = await create_business(
            session, "TiffinBox", "healthy Bengali lunch subscription, 3000 BDT/month, Dhaka"
        )
        profile = _persona()
        profile.business_id = business.id
        await save_persona(session, profile)

    memory = MemoryService(session_maker, HashEmbedding())
    engine = InterviewEngine(llm, session_maker, memory=memory)
    conversation = await engine.start(profile.id, "pricing & willingness to pay")

    turns: list[dict] = []
    total_ms = 0.0
    for q in QUESTIONS:
        t0 = time.perf_counter()
        result = await engine.ask(conversation.id, q)
        ms = (time.perf_counter() - t0) * 1000
        total_ms += ms
        turns.append(
            {
                "question": q,
                "reply": result["reply"],
                "served_by": result.get("served_by"),
                "latency_ms": round(ms),
            }
        )
        print(f"  [{tag}] {round(ms):>6}ms  {result.get('served_by')}")
    await engine_db.dispose()
    return {"tag": tag, "turns": turns, "total_ms": round(total_ms), "avg_ms": round(total_ms / len(QUESTIONS))}


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


async def main() -> None:
    print("== Arm A: local", LOCAL_MODEL)
    local = SingleAdapterLLMService(PinnedModel(OllamaAdapter(), LOCAL_MODEL))
    run_a = await run_interview(local, f"local/{LOCAL_MODEL}")

    print("== Arm B: freellmpool routing=fast")
    cloud_adapter = FreellmpoolAdapter(routing="fast")
    cloud = SingleAdapterLLMService(cloud_adapter)
    run_b = await run_interview(cloud, "freellmpool/fast")

    print("== Judging (blind labels A/B)")
    verdict = await judge(cloud, run_a, run_b)
    a, b = verdict["scores"]["A"], verdict["scores"]["B"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bar": 8.0,
        "rubric_weights": RUBRIC,
        "arm_a": {"model": f"ollama/{LOCAL_MODEL}", **run_a, "weighted": weighted(a), "dims": a},
        "arm_b": {"model": "freellmpool/fast (see served_by)", **run_b, "weighted": weighted(b), "dims": b},
        "judge": {"route": verdict["judge_route"], "notes": verdict["scores"].get("notes")},
    }
    out = REPO / "data" / "metadata" / f"local_3b_gate_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nA local/{LOCAL_MODEL}:  weighted {report['arm_a']['weighted']}/10  avg {run_a['avg_ms']}ms")
    print(f"B freellmpool/fast:     weighted {report['arm_b']['weighted']}/10  avg {run_b['avg_ms']}ms")
    print(f"judge: {verdict['judge_route']}")
    print(f"report: {out}")
    verdict_line = (
        f"GATE {'PASS' if report['arm_a']['weighted'] >= 8.0 else 'FAIL'}: "
        f"local 3B {'meets' if report['arm_a']['weighted'] >= 8.0 else 'below'} the 8/10 bar"
    )
    print(verdict_line)


if __name__ == "__main__":
    asyncio.run(main())
