"""Report generator for formatting evaluation results into Markdown and JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from bebshax.evaluation.types import EvaluationSuiteResult


class ReportGenerator:
    """Formats EvaluationSuiteResult into Markdown and JSON documents."""

    def to_markdown(self, result: EvaluationSuiteResult) -> str:
        lines: list[str] = [
            f"# BebshaX Evaluation Report — {result.timestamp}",
            "",
            f"**Suite Type:** `{result.suite_type}`",
            "",
        ]

        if result.persona_metrics:
            lines.extend([
                "## 1. Persona Quality & Grounding Metrics",
                "",
                "| Persona ID | Valid | Grounding Ratio | Consistency Score | Contradiction Count | Violations |",
                "|---|---|---|---|---|---|",
            ])
            for pm in result.persona_metrics:
                viol_str = ", ".join(pm.violations) if pm.violations else "None"
                lines.append(
                    f"| `{pm.persona_id}` | {'✅' if pm.is_valid else '❌'} | `{pm.grounding_ratio:.2%}` | `{pm.consistency_score:.2f}` | `{pm.contradiction_count}` | {viol_str} |"
                )
            lines.append("")

        if result.routing_metrics:
            lines.extend([
                "## 2. Routing Strategy Chaos Simulation",
                "",
                "| Strategy | Requests | Success Rate | Fallback Count | Latency P50 | Latency P95 | Context Failures |",
                "|---|---|---|---|---|---|---|",
            ])
            for rm in result.routing_metrics:
                lines.append(
                    f"| **{rm.strategy_name}** | {rm.total_requests} | `{rm.success_rate_pct:.1f}%` | {rm.fallback_count} | `{rm.latency_p50_ms:.1f} ms` | `{rm.latency_p95_ms:.1f} ms` | {rm.context_overflow_failures} |"
                )
            lines.append("")

        if result.offline_metrics:
            lines.extend([
                "## 3. Offline Benchmark Replay (vs Literature)",
                "",
            ])
            for om in result.offline_metrics:
                lines.extend([
                    f"### Dataset: `{om.dataset_name}` ({om.total_samples} samples)",
                    "",
                    "| Strategy | Alignment Score / Top-Match Rate |",
                    "|---|---|",
                ])
                for strat, score in om.strategy_scores.items():
                    lines.append(f"| **{strat}** | `{score:.2%}` |")
                lines.append("")

        return "\n".join(lines)

    def write_reports(
        self,
        result: EvaluationSuiteResult,
        output_dir: Path | str = "data/metadata",
        filename_prefix: str = "eval_report",
    ) -> tuple[Path, Path]:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        md_file = out_path / f"{filename_prefix}_{result.timestamp}.md"
        json_file = out_path / f"{filename_prefix}_{result.timestamp}.json"

        md_content = self.to_markdown(result)
        json_content = result.model_dump_json(indent=2)

        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        with open(json_file, "w", encoding="utf-8") as f:
            f.write(json_content)

        return md_file, json_file
