"""Tests for persona constraint validator."""

import pytest
from bebshax.datasets.validator import validate_persona_against_constraints


def test_validator_detects_valid_persona():
    segment = {
        "name": "Budget-conscious student",
        "constraints": {
            "age_range": [18, 26],
            "median_age": 22,
            "monthly_budget": {"min": 200, "median": 450, "max": 600, "currency": "BDT"},
        },
    }
    persona = {
        "name": "Samiul Alam",
        "age": 22,
        "income_range": "৳450 per month",
        "description": "Student looking for deals within ৳450 monthly budget.",
        "goals": [{"value": "Save money", "provenance": "OBSERVED", "evidence_ids": ["ev_1"]}],
    }

    result = validate_persona_against_constraints(persona, segment)
    assert result["status"] == "VALID"
    assert result["is_valid"] is True
    assert len(result["violations"]) == 0


def test_validator_detects_contradiction():
    segment = {
        "name": "Budget-conscious student",
        "constraints": {
            "age_range": [18, 24],
            "median_age": 21,
            "monthly_budget": {"min": 200, "median": 400, "max": 500, "currency": "BDT"},
        },
    }
    # Persona claims ৳2,500 monthly budget (way beyond ৳500 max) and age 45
    persona = {
        "name": "Wealthy Executive",
        "age": 45,
        "income_range": "৳2500 per month",
        "description": "High net worth individual willing to spend ৳2500 per month.",
        "goals": [{"value": "Luxury features", "provenance": "INFERRED", "evidence_ids": []}],
    }

    result = validate_persona_against_constraints(persona, segment)
    assert result["status"] == "CONTRADICTION"
    assert result["is_valid"] is False
    assert len(result["violations"]) >= 1
