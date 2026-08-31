"""Dataset Evaluator & Diversity Ranker for BebshaX.

Implements deterministic, explainable scoring formulas:
- Relevance Score (business domain, geographic match, population alignment, variable coverage)
- Quality Score (sample size, completeness, source authority, licensing)
- Diversity Filter (selects complementary domain categories, prevents redundant datasets)
- Auto-Import Thresholds & Decision Logic
"""

from __future__ import annotations

import re
from typing import Any
from bebshax.datasets.discovery.base_adapter import DatasetCandidateData, DatasetEvaluationResult
from bebshax.research.planner import DatasetRequirementSpec


class DatasetEvaluator:
    """Evaluates, scores, and selects optimal dataset candidates."""

    def __init__(self, max_auto_select: int = 4) -> None:
        self.max_auto_select = max_auto_select

    def calculate_relevance_score(
        self,
        candidate: DatasetCandidateData,
        idea: str,
        requirements: list[DatasetRequirementSpec],
    ) -> tuple[float, list[str]]:
        """Calculate deterministic relevance score between 0.50 and 0.98 and reasons."""
        score = 0.70
        reasons: list[str] = []
        lower_idea = idea.lower()
        candidate_text = (
            candidate.name + " " + candidate.description + " " + candidate.population_coverage + " " + candidate.category
        ).lower()

        # 1. Geographic relevance
        if "bangladesh" in candidate.geographic_coverage.lower() or "dhaka" in candidate.geographic_coverage.lower():
            score += 0.12
            reasons.append("Covers primary target geography (Bangladesh)")
        elif "south asia" in candidate.geographic_coverage.lower():
            score += 0.06
            reasons.append("Covers regional South Asian market baseline")
        else:
            score += 0.02
            reasons.append("Provides broader contextual macro evidence")

        # 2. Population relevance
        if "student" in lower_idea and "student" in candidate_text:
            score += 0.08
            reasons.append("Directly targets core demographic (University & Tertiary Students)")
        elif any(k in lower_idea for k in ["sme", "restaurant", "business", "shop"]) and any(
            k in candidate_text for k in ["sme", "enterprise", "firm", "retail", "pos"]
        ):
            score += 0.08
            reasons.append("Directly matches target enterprise cohort (SME & Retail Operators)")
        elif any(k in lower_idea for k in ["food", "meal", "diet"]) and any(
            k in candidate_text for k in ["food", "diet", "meal", "expenditure"]
        ):
            score += 0.08
            reasons.append("Directly matches food consumption and dietary spending behaviors")

        # 3. Variable requirements alignment
        matching_vars = 0
        for req in requirements:
            for tv in req.target_variables:
                if any(rv.lower() in tv.lower() or tv.lower() in rv.lower() for rv in candidate.relevant_variables):
                    matching_vars += 1

        if matching_vars >= 3:
            score += 0.06
            reasons.append(f"Contains {matching_vars} high-signal empirical variables required for segmentation")
        elif matching_vars >= 1:
            score += 0.03
            reasons.append(f"Contains key required variables: {', '.join(candidate.relevant_variables[:3])}")

        # Clamp between 0.50 and 0.98
        clamped_score = max(0.50, min(0.98, round(score, 2)))
        return clamped_score, reasons

    def calculate_quality_score(
        self,
        candidate: DatasetCandidateData,
    ) -> tuple[float, list[str]]:
        """Calculate deterministic dataset quality score based on authority, sample size, and license."""
        score = 0.75
        reasons: list[str] = []

        # 1. Source authority (labels are honest "modeled on <source>" strings —
        # the boost ranks by the rigor of the modeled-on methodology, not by
        # claiming real publication)
        if "bureau of statistics" in candidate.publisher.lower() or "world bank" in candidate.publisher.lower() or "ministry" in candidate.publisher.lower():
            score += 0.12
            reasons.append(f"Modeled on an authoritative statistical source: {candidate.publisher}")
        elif "verified" in candidate.publisher.lower() or "consortium" in candidate.publisher.lower() or "academic" in candidate.publisher.lower():
            score += 0.08
            reasons.append(f"Modeled on a verified research source: {candidate.publisher}")
        else:
            score += 0.04
            reasons.append("Illustrative catalog entry with documented generation methodology")

        # 2. Sample size
        if candidate.sample_rows >= 5000:
            score += 0.08
            reasons.append(f"Large statistical sample size ({candidate.sample_rows:,} records)")
        elif candidate.sample_rows >= 1000:
            score += 0.05
            reasons.append(f"Robust statistical sample size ({candidate.sample_rows:,} records)")
        else:
            score += 0.02
            reasons.append(f"Standard sample size ({candidate.sample_rows:,} records)")

        # 3. License clarity
        if any(lic in candidate.license.lower() for lic in ["open", "creative commons", "cc-by", "public domain", "government"]):
            score += 0.04
            reasons.append(f"Permitted open license: {candidate.license}")

        # Clamp between 0.50 and 0.98
        clamped_score = max(0.50, min(0.98, round(score, 2)))
        return clamped_score, reasons

    def evaluate_candidates(
        self,
        candidates: list[DatasetCandidateData],
        idea: str,
        requirements: list[DatasetRequirementSpec],
    ) -> list[DatasetEvaluationResult]:
        """Evaluate, score, and select top diverse dataset candidates."""
        evaluated: list[DatasetEvaluationResult] = []

        for cand in candidates:
            rel_score, rel_reasons = self.calculate_relevance_score(cand, idea, requirements)
            qual_score, qual_reasons = self.calculate_quality_score(cand)

            combined_reasons = rel_reasons + qual_reasons
            reason_text = " • " + "\n• ".join(combined_reasons)

            evaluated.append(
                DatasetEvaluationResult(
                    candidate=cand,
                    relevance_score=rel_score,
                    quality_score=qual_score,
                    is_selected=False,
                    selection_status="discovered",
                    selection_reason=reason_text,
                    evaluation_details={
                        "relevance_reasons": rel_reasons,
                        "quality_reasons": qual_reasons,
                        "composite_score": round((rel_score * 0.6) + (qual_score * 0.4), 2),
                    },
                )
            )

        # Sort by composite score descending
        evaluated.sort(key=lambda x: x.evaluation_details["composite_score"], reverse=True)

        # Diversity selection: select top candidates across distinct categories
        selected_categories: set[str] = set()
        selected_count = 0

        # Pass 1: pick highest scoring candidate per distinct category
        for res in evaluated:
            if selected_count >= self.max_auto_select:
                break
            if res.relevance_score >= 0.75 and res.quality_score >= 0.75:
                if res.candidate.category not in selected_categories:
                    res.is_selected = True
                    res.selection_status = "selected"
                    selected_categories.add(res.candidate.category)
                    selected_count += 1

        # Pass 2: fill remaining quota up to max_auto_select if slots remain
        if selected_count < self.max_auto_select:
            for res in evaluated:
                if selected_count >= self.max_auto_select:
                    break
                if not res.is_selected and res.relevance_score >= 0.70 and res.quality_score >= 0.70:
                    res.is_selected = True
                    res.selection_status = "selected"
                    selected_count += 1

        return evaluated
