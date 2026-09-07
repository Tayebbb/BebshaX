#!/usr/bin/env python3
"""Evaluation runner CLI script for BebshaX.

Usage:
  python scripts/run_evaluation.py --suite personas|routing|offline|all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to sys.path if running as script from repo root
repo_root = Path(__file__).resolve().parent.parent
backend_path = repo_root / "apps" / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from bebshax.evaluation import (
    EvaluationSuiteResult,
    OfflineEvaluator,
    PersonaEvaluator,
    ReportGenerator,
    RoutingChaosSimulator,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="BebshaX Quality & Routing Evaluation Suite")
    parser.add_argument(
        "--suite",
        choices=["personas", "routing", "offline", "all"],
        default="all",
        help="Evaluation suite to execute (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/metadata",
        help="Directory to save generated evaluation reports (default: data/metadata)",
    )
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    result = EvaluationSuiteResult(timestamp=timestamp, suite_type=args.suite)

    # 1. Persona Quality Evaluation
    if args.suite in ("personas", "all"):
        print("[1/3] Running Persona Quality Evaluation...")
        evaluator = PersonaEvaluator()
        sample_personas = [
            {
                "id": "pers-001",
                "name": "Sarah Chen",
                "business_id": "biz-01",
                "age": 34,
                "occupation": "Senior Product Designer",
                "goals": ["Streamline design ops", "Improve component accessibility"],
                "pain_points": ["Tool fragmentation", "Slow feedback loops"],
                "attributes": [
                    {"key": "tech_savviness", "value": "High", "provenance_class": "OBSERVED", "evidence": ["EVID-101"]},
                    {"key": "budget_tier", "value": "Enterprise", "provenance_class": "INFERRED"},
                ],
            },
            {
                "id": "pers-002",
                "name": "Alex Rivera",
                "business_id": "biz-01",
                "age": 16,
                "occupation": "Senior Executive Director",  # Rule violation: age 16 executive
                "goals": ["Expand market share"],
                "pain_points": ["Budget limits"],
                "attributes": [
                    {"key": "spending", "value": "budget", "provenance_class": "SYNTHETIC"},
                    {"key": "preferences", "value": "luxury only", "provenance_class": "SYNTHETIC"},  # Contradiction
                ],
            },
        ]

        for p in sample_personas:
            res = evaluator.evaluate(p)
            result.persona_metrics.append(res)
        print(f"     Evaluated {len(result.persona_metrics)} persona samples.")

    # 2. Routing Strategy Chaos Simulation
    if args.suite in ("routing", "all"):
        print("[2/3] Running Routing Strategy Chaos Simulation...")
        simulator = RoutingChaosSimulator(request_count=35)
        sim_results = await simulator.run_all_strategies()
        result.routing_metrics.extend(sim_results)
        print(f"     Simulated {len(result.routing_metrics)} routing strategies under chaos.")

    # 3. Offline Benchmark Replay Evaluation
    if args.suite in ("offline", "all"):
        print("[3/3] Running Offline Dataset Benchmark Replay...")
        offline_eval = OfflineEvaluator()
        ra_res = offline_eval.evaluate_router_arena()
        xb_res = offline_eval.evaluate_xroute_bench()
        result.offline_metrics.extend([ra_res, xb_res])
        print(f"     Replayed {len(result.offline_metrics)} benchmark dataset suites.")

    # Generate reports
    generator = ReportGenerator()
    md_file, json_file = generator.write_reports(result, output_dir=args.output_dir)

    print("\n[OK] Evaluation complete!")
    print(f"   Markdown Report: {md_file}")
    print(f"   JSON Report:     {json_file}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
