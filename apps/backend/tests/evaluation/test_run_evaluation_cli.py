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
