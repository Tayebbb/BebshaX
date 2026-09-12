#!/usr/bin/env python3
"""Cross-route persona consistency evaluation (the research question's metric).

K personas x Q questions x M routes x repeats through the REAL PoolRouter, then
identity-fact retention, numeric divergence, cross-route vs. baseline answer
agreement (ratio > 1 => persona signal dominates provider signal), the interview
engine's contradiction detector, and full provenance per answer.

  # offline pipeline check — scripted FakeAdapter replies, no network:
  python scripts/run_cross_route_eval.py --fake --personas 3 --questions 5 \
      --routes fakeA/m1,fakeB/m2 --repeats 2 --seed 42

    # real routes: the independent remote tiers. freellmpool is ONE virtual
  # candidate ("freellmpool/auto"); the concrete provider it picked (llm7,
  # kilo, …) is recorded per row in served_by. Requesting "llm7/codestral-latest"
  # directly cannot be honoured (no such candidate) and is reported as such.
  python scripts/run_cross_route_eval.py --personas 3 --questions 5 \
    --routes freellmpool/auto,openrouter/* --repeats 3 --allow-network

Writes <output>.json (rows + aggregates + bootstrap CIs) and a sibling .md
summary. Route preference is advisory in PoolRouter: rows record which route
actually served and whether the request was honoured — nothing is relabelled,
and cross_route_agreement pairs answers by the route that SERVED (None when a
single route served everything).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bebshax.evaluation.cross_route_consistency import CrossRouteReport

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "apps" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("BEBSHAX_JWT_SECRET", "x" * 40)  # config import guard for scripts
os.environ.setdefault("FREELLMPOOL_CONFIG", str(REPO / "providers.toml"))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from bebshax.evaluation.cross_route_consistency import PERSONA_BANK, QUESTION_BANK

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--personas", type=int, default=3, help=f"number of personas (1..{len(PERSONA_BANK)})")
    parser.add_argument("--questions", type=int, default=len(QUESTION_BANK), help=f"number of questions (1..{len(QUESTION_BANK)})")
    parser.add_argument("--routes", default="freellmpool/auto,openrouter/*", help="comma-separated approved remote provider/model routes ('*' = any)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=None, help="JSON path (default data/metadata/cross_route_<ts>.json)")
    parser.add_argument("--fake", action="store_true", help="scripted FakeAdapter routes - offline pipeline check, not a model measurement")
    parser.add_argument("--allow-network", action="store_true", help="explicitly permit real remote inference")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> tuple[CrossRouteReport, Path, Path]:
    if not args.fake and not args.allow_network:
        raise SystemExit("Real inference requires --allow-network; --fake is the no-network check")
    from bebshax.evaluation.cross_route_consistency import (
        PERSONA_BANK,
        QUESTION_BANK,
        Route,
        run_cross_route_eval,
        scripted_router,
        to_markdown,
    )

    if not 1 <= args.personas <= len(PERSONA_BANK):
        raise SystemExit(f"--personas must be 1..{len(PERSONA_BANK)}")
    if not 1 <= args.questions <= len(QUESTION_BANK):
        raise SystemExit(f"--questions must be 1..{len(QUESTION_BANK)}")
    routes = [Route.parse(spec) for spec in args.routes.split(",") if spec.strip()]
    if not args.fake and any(route.provider not in {"freellmpool", "openrouter"} for route in routes):
        raise SystemExit("Only the approved independent remote tiers may be evaluated")
    if len(routes) < 2:
        raise SystemExit("--routes needs at least two provider/model routes to compare")
    personas = list(PERSONA_BANK[: args.personas])
    questions = list(QUESTION_BANK[: args.questions])

    notes: list[str] = []
    async with AsyncExitStack() as cleanup:
        if args.fake:
            llm = scripted_router(routes)
            notes.append(
                "SIMULATED: replies are scripted from the identity card by ScriptedRouteAdapter — "
                "this run validates the pipeline and metric code, it says nothing about any model."
            )
        else:
            from scripts.ops.remote_probe import synthetic_probe_router

            llm = await cleanup.enter_async_context(synthetic_probe_router())
            notes.append("provenance_persisted=False: rows carry served_by/attempts; llm_requests was not written")
        report = await run_cross_route_eval(
            llm, personas, questions, routes,
            repeats=args.repeats, seed=args.seed, simulated=args.fake, notes=notes,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = Path(args.output) if args.output else REPO / "data" / "metadata" / f"cross_route_{stamp}.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = json_path.with_suffix(".md")
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return report, json_path, md_path


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252; route names and report text are UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = _parse_args(argv)
    report, json_path, md_path = asyncio.run(_run(args))

    def fmt(value: float | None) -> str:
        return "not measured" if value is None else f"{value:.3f}"

    print(f"kind={report.kind} simulated={report.simulated} rows={report.n_rows} served={report.n_served} failed={report.n_failed}")
    print(f"identity_fact_retention={fmt(report.identity_fact_retention)} (n={report.n_probed_facts})")
    print(f"cross_route_agreement={fmt(report.cross_route_agreement)} baseline={fmt(report.baseline_agreement)} ratio={fmt(report.agreement_ratio)}")
    print(f"contradiction_count={report.contradiction_count}  numeric_divergence_mean_bdt={fmt(report.numeric_divergence_mean_bdt)}")
    print(f"json: {json_path}\nmd:   {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
