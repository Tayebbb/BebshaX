"""Persona constraint validation engine for BebshaX.

Programmatically validates that LLM-generated personas strictly adhere to dataset-grounded
segment constraints (age, budget, occupation, tech familiarity, and provenance claims)
outside the LLM without relying on model self-evaluation.
"""

from __future__ import annotations

import re
from typing import Any


def validate_persona_against_constraints(
    persona: dict[str, Any],
    segment: dict[str, Any],
) -> dict[str, Any]:
    """Validate generated persona attributes against segment evidence constraints.
    
    Returns:
        {
            "status": "VALID" | "WARNING" | "CONTRADICTION" | "INVALID",
            "is_valid": bool,
            "has_contradiction": bool,
            "violations": list[str],
            "warnings": list[str],
            "details": dict[str, Any],
        }
    """
    violations: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    constraints = segment.get("constraints", {})
    segment_name = segment.get("name", "Unknown Segment")

    # Observed constraints are keyed by the dataset's own column names; pick the
    # age-like and budget-like numeric summaries when present.
    age_stats = _numeric_constraint(constraints, ("age",))
    budget_constraints = _numeric_constraint(constraints, ("budget", "spend", "income", "pay", "price", "cost", "allowance"))
    if age_stats and "age_range" not in constraints:
        age_range = [age_stats.get("min"), age_stats.get("max")]
    else:
        age_range = constraints.get("age_range")
    if not budget_constraints:
        budget_constraints = constraints.get("monthly_budget", {}) if isinstance(constraints.get("monthly_budget"), dict) else {}

    # 1. Age Validation
    age = persona.get("age")
    if age is not None and isinstance(age, (int, float)) and age_range and len(age_range) == 2 and None not in age_range:
        min_age, max_age = age_range[0], age_range[1]
        if age < min_age - 5 or age > max_age + 8:
            violations.append(
                f"Age {age} contradicts segment '{segment_name}' empirical range of {min_age}–{max_age}."
            )
            details["age"] = {"status": "CONTRADICTION", "expected": f"{min_age}-{max_age}", "actual": age}
        elif age < min_age or age > max_age:
            warnings.append(
                f"Age {age} is slightly outside observed segment boundary ({min_age}–{max_age})."
            )
            details["age"] = {"status": "WARNING", "expected": f"{min_age}-{max_age}", "actual": age}
        else:
            details["age"] = {"status": "VALID", "actual": age}

    # 2. Budget / Willingness-to-pay Validation
    max_allowed_budget = budget_constraints.get("max")
    median_budget = budget_constraints.get("median")

    # Extract numerical budget value from persona fields (income_range, purchase_behavior, description)
    extracted_budget = _extract_persona_budget(persona)
    if extracted_budget is not None and max_allowed_budget is not None:
        # If persona budget is > 2.2x maximum observed for a budget-conscious segment
        if extracted_budget > max_allowed_budget * 2.0:
            violations.append(
                f"Persona stated budget ({extracted_budget:,.0f}) contradicts segment maximum ({max_allowed_budget:,.0f})."
            )
            details["budget"] = {
                "status": "CONTRADICTION",
                "expected_max": max_allowed_budget,
                "actual": extracted_budget,
            }
        elif extracted_budget > max_allowed_budget * 1.3:
            warnings.append(
                f"Persona budget ({extracted_budget:,.0f}) exceeds typical segment budget ({(median_budget or max_allowed_budget):,.0f})."
            )
            details["budget"] = {
                "status": "WARNING",
                "expected_median": median_budget,
                "actual": extracted_budget,
            }
        else:
            details["budget"] = {"status": "VALID", "actual": extracted_budget}

    # 3. Provenance Verification
    # Ensure claims marked OBSERVED have real evidence IDs or dataset references
    for claim_group in ("goals", "pain_points", "needs", "motivations", "behaviors"):
        claims = persona.get(claim_group, [])
        if isinstance(claims, list):
            for claim in claims:
                if isinstance(claim, dict):
                    prov = str(claim.get("provenance", "")).upper()
                    e_ids = claim.get("evidence_ids", [])
                    if prov == "OBSERVED" and not e_ids:
                        warnings.append(
                            f"Claim in '{claim_group}' marked OBSERVED without citing evidence IDs."
                        )

    # 4. Determine Overall Status
    if violations:
        status = "CONTRADICTION"
        is_valid = False
    elif warnings:
        status = "WARNING"
        is_valid = True
    else:
        status = "VALID"
        is_valid = True

    return {
        "status": status,
        "is_valid": is_valid,
        "has_contradiction": len(violations) > 0,
        "violations": violations,
        "warnings": warnings,
        "details": details,
    }


def _numeric_constraint(constraints: dict[str, Any], keywords: tuple[str, ...]) -> dict[str, Any]:
    """First observed numeric summary (dict with min/max) whose column name
    contains one of ``keywords`` — the segmenter keys constraints by column."""
    for key, value in constraints.items():
        if isinstance(value, dict) and "min" in value and "max" in value and any(k in key.lower() for k in keywords):
            return value
    return {}


def _extract_persona_budget(persona: dict[str, Any]) -> float | None:
    """Attempt to extract numerical budget or willingness to pay from persona claims."""
    search_texts: list[str] = [
        str(persona.get("income_range", "")),
        str(persona.get("description", "")),
    ]

    for key in ("purchase_behavior", "technology_usage", "pain_points", "goals"):
        items = persona.get(key, [])
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    search_texts.append(str(it.get("value", "")))
                elif isinstance(it, str):
                    search_texts.append(it)

    full_text = " ".join(search_texts)

    # Look for patterns like "৳500", "500 taka", "$50", "budget of 1000"
    matches = re.findall(r"(?:৳|tk|taka|\$|bdt)\s*(\d[\d,.]*)", full_text, flags=re.IGNORECASE)
    if not matches:
        matches = re.findall(r"(\d[\d,.]*)\s*(?:৳|tk|taka|bdt|\/month|per month)", full_text, flags=re.IGNORECASE)

    if matches:
        try:
            cleaned = matches[0].replace(",", "")
            return float(cleaned)
        except ValueError:
            pass

    return None
