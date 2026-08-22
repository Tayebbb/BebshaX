"""Unit tests for PersonaEvaluator."""

from bebshax.evaluation.persona_evaluator import PersonaEvaluator


def test_valid_grounded_persona():
    persona = {
        "id": "pers-test-1",
        "name": "Jane Doe",
        "business_id": "biz-1",
        "age": 30,
        "occupation": "Marketing Director",
        "goals": ["Increase ROI"],
        "pain_points": ["Manual reporting"],
        "attributes": [
            {"key": "experience", "value": "10 yrs", "provenance_class": "OBSERVED", "evidence": ["E1"]},
            {"key": "team_size", "value": "15", "provenance_class": "OBSERVED", "evidence": ["E2"]},
        ],
    }

    evaluator = PersonaEvaluator()
    res = evaluator.evaluate(persona)

    assert res.persona_id == "pers-test-1"
    assert res.is_valid is True
    assert res.missing_required_fields == []
    assert res.grounding_ratio == 1.0
    assert res.consistency_score == 1.0
    assert res.contradiction_count == 0


def test_invalid_persona_missing_fields():
    persona = {
        "id": "pers-test-2",
        "name": "Incomplete Persona",
    }

    evaluator = PersonaEvaluator()
    res = evaluator.evaluate(persona)

    assert res.is_valid is False
    assert "business_id" in res.missing_required_fields
    assert "age" in res.missing_required_fields
    assert "occupation" in res.missing_required_fields


def test_persona_contradictions_and_rule_violations():
    persona = {
        "id": "pers-test-3",
        "name": "Contradictory Persona",
        "business_id": "biz-1",
        "age": 14,
        "occupation": "Senior Software Architect",  # Rule violation
        "goals": ["budget shopper"],
        "pain_points": ["luxury only"],  # Contradiction pair: budget vs luxury only
        "attributes": [],
    }

    evaluator = PersonaEvaluator()
    res = evaluator.evaluate(persona)

    assert res.is_valid is True
    assert res.contradiction_count == 1
    assert len(res.violations) >= 2
    assert res.consistency_score < 1.0
