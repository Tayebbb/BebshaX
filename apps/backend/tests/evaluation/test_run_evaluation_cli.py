"""Integration test for evaluation CLI script and report generation."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from bebshax.evaluation import (
    EvaluationSuiteResult,
    OfflineEvaluator,
    PersonaEvaluator,
    ReportGenerator,
    RoutingChaosSimulator,
)


def test_report_generator_markdown_and_json(tmp_path: Path):
    result = EvaluationSuiteResult(timestamp="20260822_150000", suite_type="all")

    evaluator = PersonaEvaluator()
    pm = evaluator.evaluate({
        "id": "p-1",
        "name": "Test Persona",
        "business_id": "b-1",
        "age": 25,
        "occupation": "Developer",
        "goals": ["Build software"],
        "pain_points": ["Bugs"],
        "attributes": [{"key": "skill", "value": "Python", "provenance_class": "OBSERVED", "evidence": ["E1"]}],
    })
    result.persona_metrics.append(pm)

    offline_eval = OfflineEvaluator()
    result.offline_metrics.append(offline_eval.evaluate_router_arena())

    generator = ReportGenerator()
    md_file, json_file = generator.write_reports(result, output_dir=tmp_path)

    assert md_file.exists()
    assert json_file.exists()
    assert md_file.stat().st_size > 0
    assert json_file.stat().st_size > 0

    with open(md_file, "r", encoding="utf-8") as f:
        md_text = f.read()
        assert "# BebshaX Evaluation Report" in md_text
        assert "Persona Quality & Grounding Metrics" in md_text
        assert "`p-1`" in md_text


def test_report_renders_unmeasured_metrics_as_prose_not_numbers(tmp_path: Path):
    from bebshax.evaluation.types import OfflineEvalResult, StrategyMetricResult

    result = EvaluationSuiteResult(timestamp="20260906_000000", suite_type="all")
    result.routing_metrics.append(StrategyMetricResult(strategy_name="HYBRID", total_requests=3))
    result.offline_metrics.append(
        OfflineEvalResult(
            dataset_name="router_arena", total_samples=809, usable_samples=0, unusable_samples=809,
            unusable=True, unusable_reason="record carries no model_scores",
            strategy_scores={"HYBRID": None, "ROUND_ROBIN": None},
        )
    )
    md = ReportGenerator().to_markdown(result)
    assert "router_control_flow_simulation" in md
    assert "| not measured |" in md  # avg_tokens_per_sec None → prose
    assert "0 usable / 809 unusable" in md and "record carries no model_scores" in md
    assert "| **HYBRID** | not measurable |" in md
    assert "120.5" not in md and "100.00%" not in md


def test_cli_execution_with_tmp_output(tmp_path: Path):
    cmd = [
        sys.executable,
        "scripts/run_evaluation.py",
        "--suite",
        "all",
        "--output-dir",
        str(tmp_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    assert proc.returncode == 0
    assert "Evaluation complete!" in proc.stdout
    md_files = list(tmp_path.glob("*.md"))
    json_files = list(tmp_path.glob("*.json"))
    assert len(md_files) >= 1
    assert len(json_files) >= 1
