"""Behavioral simulation replies are fitted to their shapes at the parse boundary.

Found live (business-matrix run, 2026-09-08): a 3B route returned
``motivators``/``objections`` as objects (``{"name": ..., "detail": ...}``) and
``key_factors`` as bare strings. Every persona had answered; the aggregate
step's ``Counter()`` then raised ``TypeError: unhashable type: 'dict'`` and the
whole run was marked failed. The model's words are kept; nothing is invented.
"""

import json

from bebshax.behavioral.engine import BehavioralSimulationEngine, _factor_items, _text_items
from bebshax.db.models import Personas

_PERSONA = Personas(id="per_shape", study_id="std_shape", name="Adesina Oluwade", status="active")


def _parse(payload: dict) -> dict:
    parsed = BehavioralSimulationEngine._parse_simulation_response(json.dumps(payload), _PERSONA)
    assert parsed is not None
    return parsed


def test_object_shaped_motivators_and_objections_keep_their_text():
    parsed = _parse(
        {
            "decision": "unlikely_to_buy",
            "probability": 0.35,
            "motivators": [{"name": "Convenience", "detail": "Lunch arrives at the desk"}, "Variety"],
            "objections": [{"title": "₦3,500 exceeds the daily lunch budget"}, {"text": "WhatsApp ordering feels informal"}],
        }
    )
    assert parsed["motivators"] == ["Convenience", "Variety"]
    assert parsed["objections"] == ["₦3,500 exceeds the daily lunch budget", "WhatsApp ordering feels informal"]


def test_bare_string_key_factors_become_factors_with_unstated_impact():
    parsed = _parse({"decision": "likely_to_buy", "probability": 0.7, "key_factors": ["Price", {"name": "Delivery time", "impact": "High"}]})
    assert parsed["key_factors"] == [
        {"name": "Price", "impact": "unstated"},
        {"name": "Delivery time", "impact": "high"},
    ]


def test_wordless_items_are_dropped_not_stringified():
    assert _text_items([None, True, {}, {"impact": "high"}, "  ", "Real objection"]) == ["Real objection"]
    assert _factor_items([{"impact": "high"}, 42]) == [{"name": "42", "impact": "unstated"}]
    assert _text_items("a single objection") == ["a single objection"]
    assert _text_items({"not": "a list"}) == []


def test_aggregate_synthesis_survives_object_shaped_lists_in_stored_rows(session_maker):
    """Rows persisted before parse-time fitting existed still aggregate."""
    engine = BehavioralSimulationEngine(None, session_maker)
    results = [
        {"persona_id": "p1", "decision": "unlikely_to_buy", "probability": 0.3, "confidence": "high", "motivators": [{"name": "Speed"}], "objections": [{"name": "Price"}, "Price"], "key_factors": ["Price"]},
        {"persona_id": "p2", "decision": "likely_to_buy", "probability": 0.8, "confidence": "medium", "motivators": ["Speed"], "objections": [], "key_factors": [{"name": "Speed", "impact": "high"}]},
    ]
    metrics, _segments, patterns, _risks, _opps, _insights = engine.compute_aggregate_synthesis(results, {}, "pricing_test")
    assert metrics["total_personas"] == 2
    assert patterns["top_motivators"] == ["Speed"]
    assert patterns["top_objections"] == ["Price"]
    assert {f["name"] for f in patterns["top_decision_factors"]} == {"Price", "Speed"}
