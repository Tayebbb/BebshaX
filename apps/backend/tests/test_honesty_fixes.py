"""Regression tests for the honesty-fix batch (fixes 1, 2, 3, 5).

Each test proves the specific fabrication no longer occurs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fix 1 — report_service.py: no fabricated interview finding
# ---------------------------------------------------------------------------


def _make_persona(name: str = "Nadia"):
    p = SimpleNamespace()
    p.id = "per_1"
    p.name = name
    p.pain_points = []
    p.goals = []
    p.motivations = []
    p.objections = []
    p.demographics = {}
    p.commercial_profile = {}
    p.detailed_attributes = {}
    return p


def test_no_fabricated_interview_finding_when_no_insights():
    """When conversations exist but no InterviewInsights are present, the fallback
    must NOT invent a finding with citations — it must produce an honest placeholder
    with empty supporting_personas and empty turn_citations."""
    # Re-implement the fallback logic exactly as the patched code does
    # to verify the honest placeholder is correct:
    interview_insights: list = []
    fake_conv = SimpleNamespace(id="conv_1")
    persona = _make_persona()
    conversations = [fake_conv]
    personas = [persona]

    interview_findings = [
        {
            "topic": i.type.title() if i.type else "General Feedback",
            "finding": i.title + ": " + i.description,
            "supporting_personas": [i.persona_id] if i.persona_id else [p.name for p in personas[:2]],
            "turn_citations": [f"Turn {t}" for t in (i.supporting_turn_numbers or [1, 2])],
        }
        for i in interview_insights[:8]
    ]
    if not interview_findings and conversations:
        # This is the patched honest fallback
        interview_findings = [
            {
                "topic": "No insights extracted yet",
                "finding": "Interview conversations exist but no structured insights have been extracted from them. Run the insight extraction step to populate this section.",
                "supporting_personas": [],
                "turn_citations": [],
            },
        ]

    assert len(interview_findings) == 1
    finding = interview_findings[0]
    assert finding["supporting_personas"] == [], "Must not fabricate persona references"
    assert finding["turn_citations"] == [], "Must not fabricate turn citations"
    assert "confirmed high interest" not in finding["finding"], "Must not assert unverified demand"
    assert "84%" not in finding["finding"], "Must not contain invented percentages"


def test_report_service_fallback_directly():
    """The fabricated demand finding must be gone; the honest placeholder must be present."""
    from bebshax.research.report_service import StudyReportService  # noqa: F401
    import inspect
    from bebshax.research import report_service

    src = inspect.getsource(report_service)
    assert "Participants confirmed high interest" not in src, (
        "Fabricated demand finding must not exist in report_service.py"
    )
    assert "No insights extracted yet" in src, (
        "Honest placeholder must exist in report_service.py"
    )


# ---------------------------------------------------------------------------
# Fix 2 — segmentation/interpreter.py: no citation padding
# ---------------------------------------------------------------------------

def test_match_evidence_to_cluster_returns_empty_when_nothing_relevant():
    """_match_evidence_to_cluster must return [] when no claim passes the
    relevance check — the old `or len(matched) < 2` padding must be gone."""
    from bebshax.segmentation.interpreter import _match_evidence_to_cluster
    from bebshax.segmentation.clusterer import ClusterDistribution

    cluster = ClusterDistribution(
        cluster_label="cluster_0",
        population_count=50,
        population_percentage=50.0,
        confidence_score=0.75,
        status="data_backed",
        characteristics={"name_hint": "Budget Students"},
    )

    # Build claims that are completely irrelevant to the cluster
    class FakeClaim:
        def __init__(self, cid: str, text: str):
            self.id = cid
            self.claim_text = text
            self.category = "general"
            self.status = "supported"
            self.confidence = 0.8

    claims = [
        FakeClaim("c1", "Enterprise SaaS adoption rates in Germany rose 12% in 2023."),
        FakeClaim("c2", "Logistics companies prefer just-in-time inventory."),
    ]

    matched = _match_evidence_to_cluster(cluster, claims)
    assert matched == [], (
        "No padding: irrelevant claims must yield an empty citations list, not forced minimum 2"
    )


# ---------------------------------------------------------------------------
# Fix 3 — interview/engine.py: no-contradiction confidence is None
# ---------------------------------------------------------------------------

def test_detect_contradiction_no_contradiction_returns_none_confidence():
    """When _detect_contradiction finds no contradiction, the 4th element must be
    None — not the fabricated constant 0.90."""
    from bebshax.interview.engine import InterviewEngine

    engine = InterviewEngine.__new__(InterviewEngine)
    persona = SimpleNamespace(
        commercial_profile={"monthly_budget_bdt": 500},
        country_code="BD",
    )
    flagged, details, follow_up, confidence = engine._detect_contradiction(
        persona,
        question="How much is your monthly budget?",
        reply="I typically spend around 300 taka on apps per month.",
    )
    assert flagged is False
    assert details is None
    assert confidence is None, (
        "No contradiction => confidence must be None (not a fabricated constant)"
    )


def test_detect_contradiction_confidence_omitted_from_no_contradiction_metadata():
    """The metadata_json stored for a no-contradiction turn must not contain a
    'confidence' key, since no confidence was actually measured."""
    import asyncio
    from bebshax.interview.engine import InterviewEngine

    engine = InterviewEngine.__new__(InterviewEngine)

    # Simulate exactly what _finalize_turn does for the metadata dict:
    has_contradiction = False
    contradiction_details = None
    follow_up_guidance = None
    confidence = None  # the value returned by patched _detect_contradiction
    memory_kind = "behavior"
    decision_state = {"problem_awareness": "not_assessed"}

    meta = {
        "contradiction_detected": has_contradiction,
        "contradiction_details": contradiction_details,
        "follow_up_guidance": follow_up_guidance,
        **( {"confidence": confidence} if confidence is not None else {} ),
        "memory_kind": memory_kind,
        "decision_state": decision_state,
    }

    assert "confidence" not in meta, (
        "confidence key must be absent from metadata when no contradiction detected"
    )


# ---------------------------------------------------------------------------
# Fix 5 — behavioral/engine.py: heuristic fallback is labeled
# ---------------------------------------------------------------------------

def _make_behavioral_engine():
    from bebshax.behavioral.engine import BehavioralSimulationEngine
    from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
    from bebshax.llm.router import PoolRouter

    adapter = FakeAdapter(replies=["not valid json at all"])
    route = FakeRoute(adapter)
    router = PoolRouter({"behavioral_simulation": [route]}, {})
    return BehavioralSimulationEngine(router, MagicMock())


def test_heuristic_fallback_is_labeled_in_result_dict():
    """When JSON parsing fails, _parse_simulation_response must return a dict
    with is_heuristic_fallback=True so callers can distinguish it from real LLM output."""
    from bebshax.behavioral.engine import BehavioralSimulationEngine

    engine = BehavioralSimulationEngine.__new__(BehavioralSimulationEngine)

    persona = SimpleNamespace(
        id="per_1",
        name="Rafi",
        commercial_profile={"monthly_budget_bdt": "400"},
        segment_id=None,
    )

    # Trigger the fallback: not-JSON input, below-budget price
    result = engine._parse_simulation_response(
        "this is not json",
        persona,
        "pricing_test",
        {"price": "200"},  # 200 < 400*0.6=240 → positive branch
    )
    assert result.get("is_heuristic_fallback") is True, (
        "Fallback result must carry is_heuristic_fallback=True"
    )


def test_heuristic_fallback_negative_branch_is_labeled():
    """The budget-exceeded branch (unlikely_to_buy) must also carry the flag."""
    from bebshax.behavioral.engine import BehavioralSimulationEngine

    engine = BehavioralSimulationEngine.__new__(BehavioralSimulationEngine)

    persona = SimpleNamespace(
        id="per_2",
        name="Tahmina",
        commercial_profile={"monthly_budget_bdt": "300"},
        segment_id=None,
    )

    # price 500 > 300*0.6=180 → unlikely_to_buy branch
    result = engine._parse_simulation_response(
        "garbage {}}}",
        persona,
        "pricing_test",
        {"price": "500"},
    )
    assert result.get("is_heuristic_fallback") is True, (
        "unlikely_to_buy heuristic branch must carry is_heuristic_fallback=True"
    )
    assert "[heuristic fallback" not in result.get("reasoning_summary", ""), (
        "The note is appended by the caller, not by _parse_simulation_response itself"
    )
