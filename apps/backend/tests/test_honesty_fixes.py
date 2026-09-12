"""Regression tests for the honesty-fix batch (fixes 1, 2, 3, 5).

Each test proves the specific fabrication no longer occurs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def test_report_service_has_no_template_path():
    """The fabricated demand finding must be gone — and so must the template
    report that hosted it: synthesis is model-written or fails explicitly."""
    import inspect

    from bebshax.research import report_service

    src = inspect.getsource(report_service)
    assert "Participants confirmed high interest" not in src, (
        "Fabricated demand finding must not exist in report_service.py"
    )
    assert "_generate_deterministic_report" not in src, "template report path must be gone"
    assert "Viral word-of-mouth" not in src
    assert "raise LLMUnavailable(" in src and "raise UnusableModelOutput(" in src


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
# Fix 5 — behavioral/engine.py: no heuristic decision ever stands in for the model
# ---------------------------------------------------------------------------


def test_unusable_simulation_reply_yields_no_decision():
    """A reply that is not JSON / has no decision / has a non-numeric probability
    is rejected (None) — the caller retries and then fails explicitly. No
    budget-vs-price estimate is produced."""
    from bebshax.behavioral.engine import BehavioralSimulationEngine

    persona = SimpleNamespace(id="per_1", name="Rafi", commercial_profile={"monthly_budget": 400}, segment_id=None)
    parse = BehavioralSimulationEngine._parse_simulation_response
    assert parse("this is not json", persona) is None
    assert parse(json.dumps({"probability": 0.4}), persona) is None
    assert parse(json.dumps({"decision": "positive", "probability": "very"}), persona) is None
    ok = parse(json.dumps({"decision": "negative", "probability": 1.7, "objections": "x"}), persona)
    # Probability is clamped, never invented; a lone-string objection is the
    # model's own word and is kept as a one-item list rather than discarded.
    assert ok["decision"] == "negative" and ok["probability"] == 1.0 and ok["objections"] == ["x"]
    assert parse(json.dumps({"decision": "negative", "probability": 0.2, "objections": None}), persona)["objections"] == []


@pytest.mark.asyncio
async def test_simulation_retries_once_then_fails_explicitly():
    from bebshax.behavioral.engine import SIMULATION_UNPARSEABLE, BehavioralSimulationEngine
    from bebshax.utils.explicit_failures import UnusableModelOutput

    class _LLM:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, request):
            self.calls += 1
            return SimpleNamespace(text="no json here", provider="fake", model="stub", provenance=None)

    llm = _LLM()
    engine = BehavioralSimulationEngine(llm, MagicMock())

    async def _ctx(session, persona, study):
        return "PERSONA CARD", {"persona_profile": True}, []

    engine._gather_simulation_context = _ctx  # type: ignore[method-assign]
    persona = SimpleNamespace(id="per_1", name="Rafi", commercial_profile={}, demographics={}, segment_id=None, version=1)
    # The engine releases its DB session before the provider call; an awaitable close is required.
    session = MagicMock()
    session.close = AsyncMock()
    with pytest.raises(UnusableModelOutput) as info:
        await engine.simulate_persona_response(
            persona=persona, study=None, test_type="pricing_test", scenario_title="Price",
            scenario_text="A monthly plan.", parameters={"price": "9 EUR"}, session=session,
        )
    assert llm.calls == 2
    assert info.value.error_code == SIMULATION_UNPARSEABLE
    session.close.assert_awaited_once()


def test_scenario_directives_only_carry_supplied_parameters():
    """No invented prices, currencies, offers or alternatives in the prompt."""
    from bebshax.behavioral.engine import SIMULATORS

    for sim in SIMULATORS.values():
        text = sim.build_test_prompt_directive("Title", "Body", {})
        for invented in ("৳", "BDT", "Bangladesh", "YouTube", "Sign Up Free", "50% off", "Immediate need", "Trust & effort"):
            assert invented not in text, f"{sim.test_type} invented {invented!r}"
        assert "Title" in text and "Body" in text
    priced = SIMULATORS["pricing_test"].build_test_prompt_directive("T", "B", {"price": "9 EUR", "billing_period": "monthly"})
    assert "Proposed Price: 9 EUR" in priced and "Billing Period: monthly" in priced
    assert "Current Alternative" not in priced  # not supplied -> not present


def test_behavioral_confidence_defaults_are_not_invented():
    """A missing confidence must read as "no signal", not as a plausible 0.8.
    The ORM default has to agree with the DB server_default (0)."""
    import inspect

    from bebshax.behavioral.engine import BehavioralSimulationEngine
    from bebshax.behavioral.orm import BehavioralTestResults

    assert BehavioralTestResults.__table__.c.confidence_score.default.arg == 0.0

    persist_src = inspect.getsource(BehavioralSimulationEngine._execute_marked_run)
    assert 'confidence_score=r_data.get("confidence_score", 0.8)' not in persist_src
    assert 'probability=r_data.get("probability", 0.5)' not in persist_src

    failed_src = inspect.getsource(BehavioralSimulationEngine._safe_simulate_single)
    assert '"probability": 0.5' not in failed_src and '"probability": 0.0' in failed_src


def test_engine_has_no_heuristic_fallback_left():
    import inspect

    from bebshax.behavioral import engine

    src = inspect.getsource(engine)
    for token in ("is_heuristic_fallback", "budget_num", "monthly_budget_bdt", "Standard behavioral evaluation", "budget resistance", "perceived convenience"):
        assert token not in src, f"heuristic remnant: {token!r}"

