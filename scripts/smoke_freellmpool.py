"""Live governed remote-routing smoke (REAL network call, explicit consent).

Run:  .venv\\Scripts\\python scripts/smoke_freellmpool.py --allow-network
Exit code 0 on success. Not part of the unit suite (RULES.md R7).
"""

import asyncio
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bebshax.llm import ChatMessage, LLMRequest, TaskType
from scripts.ops.remote_probe import synthetic_probe_router


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-network", action="store_true")
    if not parser.parse_args(argv).allow_network:
        parser.error("Real remote inference requires --allow-network")
    request = LLMRequest(
        task=TaskType.EMERGENCY_FALLBACK,
        messages=[
            ChatMessage(
                role="user",
                content="Reply with one short sentence confirming BebshaX routing works.",
            )
        ],
        max_output_tokens=48,
    )
    try:
        async with synthetic_probe_router() as service:
            result = await service.complete(request)
    except Exception as exc:  # noqa: BLE001 — smoke script reports anything
        print(f"SMOKE FAILED: {type(exc).__name__}")
        return 1

    p = result.provenance
    print("SMOKE OK")
    print(f"  served_by : {p.served_by_provider}/{p.served_by_model}")
    print(f"  latency   : {p.total_latency_ms:.0f} ms")
    print(f"  tokens    : in={result.usage.input_tokens} out={result.usage.output_tokens}")
    print(f"  attempts  : {len(p.attempts)}")
    print("Scope: one governed remote response, not a fleet availability guarantee")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
