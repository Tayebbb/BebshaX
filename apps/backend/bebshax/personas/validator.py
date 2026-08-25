"""Deterministic validation and grounding score computation for synthetic personas."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ValidationOutcome(BaseModel):
    is_valid: bool
    status: str  # ready, needs_review
    grounding_score: float
    confidence: float
    warnings: list[str] = Field(default_factory=list)


def validate_synthetic_persona(
    persona_dict: dict[str, Any],
    segment_characteristics: dict[str, Any],
    evidence_claims: list[Any] | None = None,
) -> ValidationOutcome:
    """Validate persona attributes against segment bounds and compute grounding score."""
    warnings: list[str] = []
    base_score = 0.85

    # 1. Demographics & Age Range Validation
    demo = persona_dict.get("demographics", {}) or {}
    age = demo.get("age")
    if age is not None:
        try:
            age_int = int(age)
            seg_demo = segment_characteristics.get("demographics", {}) or {}
            seg_age_range = seg_demo.get("age_range")
            if isinstance(seg_age_range, (list, tuple)) and len(seg_age_range) == 2:
                min_age, max_age = seg_age_range[0] - 2, seg_age_range[1] + 2
                if not (min_age <= age_int <= max_age):
                    warnings.append(
                        f"Age ({age_int}) falls outside segment expected range ({seg_age_range[0]}–{seg_age_range[1]})."
                    )
            else:
                base_score += 0.03
        except (ValueError, TypeError):
            warnings.append("Age is not a valid integer.")

    # 2. Economic & Monthly Budget Validation
    comm = persona_dict.get("commercial_profile", {}) or {}
    budget = comm.get("monthly_budget_bdt")
    if budget is not None:
        try:
            budget_num = float(budget)
            seg_econ = segment_characteristics.get("economics", {}).get("monthly_budget", {}) or {}
            if isinstance(seg_econ, dict):
                min_b = float(seg_econ.get("min", 200)) * 0.7
                max_b = float(seg_econ.get("max", 1500)) * 1.3
                if not (min_b <= budget_num <= max_b):
                    warnings.append(
                        f"Monthly budget (৳{budget_num:.0f}) deviates significantly from segment bounds (৳{seg_econ.get('min', 200)}–৳{seg_econ.get('max', 1000)})."
                    )
                else:
                    base_score += 0.04
        except (ValueError, TypeError):
            pass

    # 3. Required Fields & Richness Checks
    name = persona_dict.get("name", "").strip()
    if not name or len(name) < 2:
        warnings.append("Persona is missing a valid name.")

    goals = persona_dict.get("goals", []) or []
    if len(goals) < 1:
        warnings.append("Persona is missing structured goals.")

    pain_points = persona_dict.get("pain_points", []) or []
    if len(pain_points) < 1:
        warnings.append("Persona is missing structured pain points.")

    needs = persona_dict.get("needs", []) or []
    if len(needs) < 1:
        warnings.append("Persona is missing structured observed needs.")

    # 4. Evidence Citations Bonus
    citations = persona_dict.get("evidence_citations", []) or []
    if len(citations) >= 1:
        base_score += 0.05

    # 5. Calculate Final Grounding Score and Status
    penalty = len(warnings) * 0.10
    final_grounding_score = max(0.50, min(0.98, round(base_score - penalty, 2)))
    confidence = max(0.70, min(0.95, round(final_grounding_score - (0.05 if warnings else 0.0), 2)))

    status = "ready" if final_grounding_score >= 0.80 and len(warnings) == 0 else "needs_review"
    is_valid = len(warnings) == 0

    return ValidationOutcome(
        is_valid=is_valid,
        status=status,
        grounding_score=final_grounding_score,
        confidence=confidence,
        warnings=warnings,
    )
