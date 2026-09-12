"""Measure real free-tier capacity (AI plan §10, step 1).

Replays a configurable mix of PERSONA_GENERATION / PERSONA_INTERVIEW-shaped
requests through the LIVE router and reports tokens + requests per concrete
provider, so the PROVIDER_QUOTAS table can be tuned against reality.

Usage: python scripts/measure_capacity.py --allow-network [--requests 6] [--concurrency 2]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bebshax.llm import ChatMessage, LLMRequest, TaskType
from scripts.ops.remote_probe import synthetic_probe_router

GEN_PROMPT = "Sketch one realistic customer persona (3 sentences) for a rural mobile-savings app."
INT_PROMPT = "As a rice farmer persona, answer in 2 sentences: how do you save after harvest?"


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_network:
        parser.error("Capacity measurement requires explicit --allow-network consent")
    if not 1 <= args.requests <= 20 or not 1 <= args.concurrency <= 2:
        parser.error("The reviewed sample budget is 1..20 requests and 1..2 concurrent calls")

    sem = asyncio.Semaphore(args.concurrency)
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"requests": 0, "tokens": 0})
    failures = 0

    async def one(i: int) -> None:
        nonlocal failures
        task, prompt = (
            (TaskType.PERSONA_GENERATION, GEN_PROMPT)
            if i % 2 == 0
            else (TaskType.PERSONA_INTERVIEW, INT_PROMPT)
        )
        async with sem:
            try:
                result = await router.complete(
                    LLMRequest(
                        task=task,
                        messages=[ChatMessage(role="user", content=prompt)],
                        max_output_tokens=200,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — measurement counts every failure kind
                failures += 1
                print(f"  #{i} FAILED: {exc.__class__.__name__}")
                return
            usage = (result.usage.input_tokens or 0) + (result.usage.output_tokens or 0)
            stats[result.provider]["requests"] += 1
            stats[result.provider]["tokens"] += usage
            print(f"  #{i} {task.value[:18]:<18} -> {result.provider}/{result.model} ({usage} tok)")

    try:
        async with synthetic_probe_router() as router:
            await asyncio.gather(*(one(i) for i in range(args.requests)))
    except Exception as error:
        print(f"CAPACITY BLOCKED: {type(error).__name__}")
        return 1

    print("\nProvider capacity sample:")
    print(f"{'provider':<16}{'requests':>9}{'tokens':>9}")
    for provider, s in sorted(stats.items()):
        print(f"{provider:<16}{s['requests']:>9}{s['tokens']:>9}")
    print(f"failures: {failures}/{args.requests}")
    return 0 if failures < args.requests else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
