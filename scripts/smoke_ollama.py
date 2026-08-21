"""Live local smoke test for the Ollama adapter (REAL local inference).

Run:  .venv\\Scripts\\python scripts/smoke_ollama.py
Exit 0 on success. Not part of the unit suite (RULES.md R7).
"""

import asyncio
import sys

from bebshax.llm import ChatMessage, LLMRequest, SingleAdapterLLMService, TaskType
from bebshax.llm.adapters.ollama_adapter import OllamaAdapter


async def main() -> int:
    adapter = OllamaAdapter()
    service = SingleAdapterLLMService(adapter)
    request = LLMRequest(
        task=TaskType.EMERGENCY_FALLBACK,
        messages=[
            ChatMessage(
                role="user",
                content="Reply with one short sentence confirming the BebshaX local fallback works.",
            )
        ],
        max_output_tokens=48,
    )
    try:
        result = await service.complete(request)
    except Exception as exc:  # noqa: BLE001 — smoke script reports anything
        print(f"SMOKE FAILED: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await adapter.aclose()

    p = result.provenance
    print("SMOKE OK")
    print(f"  served_by : {p.served_by_provider}/{p.served_by_model}")
    print(f"  latency   : {p.total_latency_ms:.0f} ms")
    print(f"  tokens    : in={p.input_tokens} out={p.output_tokens}")
    print(f"  notes     : {p.attempts[-1].notes}")
    print(f"  reply     : {result.text.strip()[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
