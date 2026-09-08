"""Deterministic validation and grounding score computation for synthetic personas.

Grounding is measured, never decorated: ``grounding_score`` is the share of the
persona's claims (goals/needs/pain points) whose provenance is OBSERVED —
actually cited to verified evidence — and ``confidence`` is the share that is
at least evidence-adjacent (OBSERVED or INFERRED). Both are 0.0 when no claim
provenance exists. Validity checks report warnings; they never inflate scores.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ValidationOutcome(BaseModel):
    is_valid: bool
    status: str  # ready, needs_review
    grounding_score: float
    confidence: float
    warnings: list[str] = Field(default_factory=list)


def _provenance_ratios(claim_provenance: dict[str, Any] | None) -> tuple[float, float]:
    """(observed/total, (observed+inferred)/total) over all claim groups; (0, 0) if empty."""
    if not claim_provenance:
        return 0.0, 0.0
    entries = [
        e
        for group in claim_provenance.values()
        if isinstance(group, list)
        for e in group
        if isinstance(e, dict)
    ]
    total = len(entries)
    if total == 0:
        return 0.0, 0.0
    observed = sum(1 for e in entries if e.get("provenance") == "OBSERVED")
    non_synthetic = sum(1 for e in entries if e.get("provenance") in ("OBSERVED", "INFERRED"))
    return round(observed / total, 2), round(non_synthetic / total, 2)


def validate_synthetic_persona(
    persona_dict: dict[str, Any],
    segment_characteristics: dict[str, Any],
    evidence_claims: list[Any] | None = None,
) -> ValidationOutcome:
    """Validate persona attributes against segment bounds and compute honest grounding."""
    warnings: list[str] = []

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
        except (ValueError, TypeError):
            warnings.append("Age is not a valid integer.")

    # 2. Economic & Monthly Budget Validation (currency-neutral: the persona's
    # own currency label is echoed, never a hard-coded symbol).
    comm = persona_dict.get("commercial_profile", {}) or {}
    budget = comm.get("monthly_budget", comm.get("monthly_budget_bdt"))
    currency = str(comm.get("currency") or ("BDT" if "monthly_budget_bdt" in comm else "")).strip()
    unit = f" {currency}" if currency else ""
    if budget is not None:
        try:
            budget_num = float(budget)
            seg_econ = segment_characteristics.get("economics", {}).get("monthly_budget", {}) or {}
            if isinstance(seg_econ, dict) and ("min" in seg_econ or "max" in seg_econ):
                min_b = float(seg_econ.get("min", 0)) * 0.7
                max_b = float(seg_econ.get("max", float("inf"))) * 1.3
                if not (min_b <= budget_num <= max_b):
                    warnings.append(
                        f"Monthly budget ({budget_num:.0f}{unit}) deviates significantly from segment bounds "
                        f"({seg_econ.get('min', '?')}–{seg_econ.get('max', '?')}{unit})."
                    )
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
        warnings.append("Persona is missing structured needs.")

    # 4. Grounding: measured from claim provenance, never from bonuses.
    grounding, confidence = _provenance_ratios(persona_dict.get("claim_provenance"))

    # "ready" means the persona passed deterministic checks — it does not
    # assert evidence support; grounding_score carries that separately.
    status = "ready" if len(warnings) == 0 else "needs_review"
    is_valid = len(warnings) == 0

    return ValidationOutcome(
        is_valid=is_valid,
        status=status,
        grounding_score=grounding,
        confidence=confidence,
        warnings=warnings,
    )
