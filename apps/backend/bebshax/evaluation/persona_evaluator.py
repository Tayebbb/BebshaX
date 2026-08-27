"""Persona quality and grounding evaluator."""

from __future__ import annotations

from typing import Any
from bebshax.evaluation.types import PersonaMetricResult

REQUIRED_PERSONA_FIELDS = [
    "id",
    "name",
    "business_id",
    "age",
    "occupation",
    "goals",
    "pain_points",
    "attributes",
]

CONTRADICTION_PAIRS = [
    ("budget", "luxury only"),
    ("vegetarian", "meat lover"),
    ("student", "retired executive"),
    ("early bird", "night owl only"),
    ("no tech experience", "senior software architect"),
]


class PersonaEvaluator:
    """Evaluates synthetic personas for schema validity, evidence grounding, rule consistency, and contradictions."""

    def evaluate(self, persona: dict[str, Any], transcript: list[dict[str, str]] | None = None) -> PersonaMetricResult:
        persona_id = str(persona.get("id", "unknown"))
        missing_fields: list[str] = []

        for req in REQUIRED_PERSONA_FIELDS:
            if req not in persona or persona[req] is None:
                missing_fields.append(req)

        is_valid = len(missing_fields) == 0

        # Calculate grounding ratio
        attributes = persona.get("attributes", [])
        if isinstance(attributes, dict):
            attributes_list = [{"key": k, "value": v} for k, v in attributes.items()]
        elif isinstance(attributes, list):
            attributes_list = attributes
        else:
            attributes_list = []

        total_attrs = len(attributes_list)
        grounded_count = 0
        for attr in attributes_list:
            if isinstance(attr, dict):
                prov = attr.get("provenance_class", "").upper()
                has_evidence = bool(attr.get("evidence_ids") or attr.get("evidence"))
                # Only evidence-cited OBSERVED claims count as grounded —
                # INFERRED text with a decorative evidence string does not.
                if prov == "OBSERVED" and has_evidence:
                    grounded_count += 1

        # Schema validity is not grounding: a persona with no attributes has
        # zero grounding, never a free 1.0.
        grounding_ratio = grounded_count / total_attrs if total_attrs > 0 else 0.0

        # Rule consistency & contradiction checks
        violations: list[str] = []
        consistency_score = 1.0

        # Check deterministic rules
        age = persona.get("age")
        occ = str(persona.get("occupation", "")).lower()
        if isinstance(age, int):
            if age < 18 and ("executive" in occ or "architect" in occ or "director" in occ):
                violations.append(f"Inconsistent age {age} for occupation '{occ}'")
            if age > 75 and "active student" in occ:
                violations.append(f"Unusual age {age} for occupation '{occ}'")

        # Contradiction scan across persona description & interview transcript
        full_text_builder: list[str] = []
        for key in ["name", "occupation", "goals", "pain_points", "description"]:
            val = persona.get(key)
            if isinstance(val, str):
                full_text_builder.append(val)
            elif isinstance(val, list):
                full_text_builder.extend([str(item) for item in val])

        if transcript:
            for turn in transcript:
                msg = turn.get("message", "")
                if msg:
                    full_text_builder.append(msg)

        full_text = " ".join(full_text_builder).lower()
        contradiction_count = 0

        for item_a, item_b in CONTRADICTION_PAIRS:
            if item_a in full_text and item_b in full_text:
                contradiction_count += 1
                violations.append(f"Contradiction detected between '{item_a}' and '{item_b}'")

        if violations:
            consistency_score = max(0.0, 1.0 - 0.25 * len(violations))

        return PersonaMetricResult(
            persona_id=persona_id,
            is_valid=is_valid,
            missing_required_fields=missing_fields,
            grounding_ratio=round(grounding_ratio, 4),
            grounded_attribute_count=grounded_count,
            total_attribute_count=total_attrs,
            consistency_score=round(consistency_score, 4),
            contradiction_count=contradiction_count,
            violations=violations,
        )
