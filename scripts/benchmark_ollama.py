"""Benchmark installed Ollama models (REAL local inference — not part of the unit suite).

Run:  .venv\\Scripts\\python scripts/benchmark_ollama.py [--runs 3] [--model NAME]
Writes data/metadata/ollama_benchmark.json and prints a table plus a
fast-model recommendation for the 4 GB VRAM ceiling (Phase 4 spec).

Uses Ollama's native /api/chat because its response carries exact nanosecond
timings (load/prompt_eval/eval durations) and token counts.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
PROMPT = "Reply with exactly: BebshaX local fallback ready."
# ~4 GB VRAM: a Q4 model file up to ~3.0 GB stays fully GPU-resident with context headroom
FULL_GPU_SIZE_LIMIT_GB = 3.0
RECOMMENDED_FAST_MODELS = [
    ("qwen3:4b", "~2.6 GB Q4 — same family as installed qwen3.5, fits 4 GB VRAM fully"),
    ("llama3.2:3b", "~2.0 GB Q4 — smaller alternative if qwen3:4b pull fails"),
]


def bench_model(client: httpx.Client, model: str, runs: int, timeout_s: float) -> dict:
    samples = []
    load_ms_first = None
    for i in range(runs):
        try:
            r = client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "stream": False,
                    "options": {"num_predict": 48, "num_ctx": 4096, "temperature": 0.0},
                },
                timeout=timeout_s,
            )
            r.raise_for_status()
        except httpx.TimeoutException:
            return {
                "model": model,
                "status": "timeout",
                "error": f"no response within {timeout_s:.0f}s on run {i + 1} "
                "(likely RAM/VRAM pressure — model cannot serve as a live fallback here)",
                "runs_completed": i,
                "samples": samples,
            }
        except httpx.HTTPError as exc:
            return {
                "model": model,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "runs_completed": i,
                "samples": samples,
            }
        d = r.json()
        eval_count = d.get("eval_count", 0)
        eval_ns = d.get("eval_duration", 0)
        total_ns = d.get("total_duration", 0)
        load_ns = d.get("load_duration", 0)
        prompt_ns = d.get("prompt_eval_duration", 0)
        if i == 0:
            load_ms_first = load_ns / 1e6
        samples.append(
            {
                "tokens_per_sec": (eval_count / eval_ns * 1e9) if eval_ns else 0.0,
                "ttft_ms": (load_ns + prompt_ns) / 1e6,
                "total_ms": total_ns / 1e6,
                "output_tokens": eval_count,
            }
        )
    return {
        "model": model,
        "status": "ok",
        "runs": runs,
        "first_load_ms": round(load_ms_first or 0, 1),
        "tokens_per_sec_median": round(statistics.median(s["tokens_per_sec"] for s in samples), 2),
        "ttft_ms_median": round(statistics.median(s["ttft_ms"] for s in samples), 1),
        "total_ms_median": round(statistics.median(s["total_ms"] for s in samples), 1),
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", help="benchmark only this model")
    parser.add_argument("--timeout", type=float, default=240.0, help="per-request timeout seconds")
    args = parser.parse_args()

    client = httpx.Client(base_url=BASE_URL)
    try:
        tags = client.get("/api/tags", timeout=5.0).json().get("models", [])
    except httpx.HTTPError as exc:
        print(f"Ollama daemon not reachable at {BASE_URL}: {exc}")
        return 1

    installed = {m["name"]: m.get("size", 0) / 1e9 for m in tags}
    targets = [args.model] if args.model else list(installed)
    if not targets:
        print("No Ollama models installed.")
        return 1

    results = []
    for model in targets:
        print(f"benchmarking {model} ({args.runs} runs, timeout {args.timeout:.0f}s) ...", flush=True)
        results.append({**bench_model(client, model, args.runs, args.timeout), "size_gb": round(installed.get(model, 0.0), 2)})

    out_path = Path("data/metadata/ollama_benchmark.json")
    existing = json.loads(out_path.read_text()) if out_path.exists() else {"results": {}}
    for res in results:
        existing["results"][res["model"]] = res
    existing["base_url"] = BASE_URL
    existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(existing, indent=2))

    print(f"\n{'model':<24}{'size GB':>8}{'status':>10}{'tok/s':>8}{'ttft ms':>10}{'total ms':>10}")
    for res in results:
        if res.get("status") == "ok":
            print(
                f"{res['model']:<24}{res['size_gb']:>8}{'ok':>10}{res['tokens_per_sec_median']:>8}"
                f"{res['ttft_ms_median']:>10}{res['total_ms_median']:>10}"
            )
        else:
            print(f"{res['model']:<24}{res['size_gb']:>8}{res.get('status', '?'):>10}  {res.get('error', '')}")
    print(f"\nwritten: {out_path}")

    if not any(size <= FULL_GPU_SIZE_LIMIT_GB for size in installed.values()):
        print("\nRECOMMENDATION (4 GB VRAM ceiling): no fully-GPU-resident model installed.")
        for name, why in RECOMMENDED_FAST_MODELS:
            print(f"  ollama pull {name:<14} # {why}")
        print("Pull the first, re-run this script, then compare tok/s before adopting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
