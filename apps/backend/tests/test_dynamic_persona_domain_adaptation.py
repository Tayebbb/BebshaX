"""
Tests for interview-engine contradiction detection & memory classification.

(The keyword "domain adaptation" tables and the deterministic template persona
they fed were removed on 2026-09-08: every persona is now written by the model
from the study's own inputs — see tests/test_persona_generation_engine.py.)
"""

from unittest.mock import MagicMock

from bebshax.interview.engine import InterviewEngine


def test_contradiction_detection_in_interview_engine():
    """Verify InterviewEngine structurally detects budget contradictions and provides guidance."""
    llm = MagicMock()
    session_maker = MagicMock()
    engine = InterviewEngine(llm, session_maker)

    mock_persona = MagicMock()
    mock_persona.commercial_profile = {"monthly_budget_bdt": 400}

    # 1. Obvious contradiction: agreeing to ৳2,500 on a ৳400 budget
    has_contra, details, follow_up, conf = engine._detect_contradiction(
        mock_persona,
        question="Would you pay ৳2,500 every month for unlimited priority orders?",
        reply="Sure, ৳2500 is great and I will gladly pay that amount right away!",
    )
    assert has_contra is True
    assert "exceeds the stated monthly budget of 400 BDT" in details
    assert "What changed your willingness to pay" in follow_up
    # A deterministic regex rule yields a boolean fact, not a calibrated
    # probability — the former constant 0.60 was invented and is gone.
    assert conf is None

    # 2. Consistent response: declining out-of-budget proposal
    has_contra2, details2, follow_up2, conf2 = engine._detect_contradiction(
        mock_persona,
        question="Would you pay ৳2,500 every month for unlimited priority orders?",
        reply="No, ৳2,500 is completely out of my monthly allowance. My maximum food app budget is around ৳400.",
    )
    assert has_contra2 is False
    assert details2 is None
    # No contradiction detected — confidence is None (not invented)
    assert conf2 is None


def test_classify_memory_type():
    """Verify 15-category memory extraction classification."""
    llm = MagicMock()
    session_maker = MagicMock()
    engine = InterviewEngine(llm, session_maker)

    assert engine._classify_memory_type("pricing_budget", "What is your budget?", "My monthly limit is ৳500") == "budget"
    assert engine._classify_memory_type("pain_points", "What annoys you?", "Deliveries are always late and cold") == "frustration"
    assert engine._classify_memory_type("current_alternatives", "What do you use now?", "I use Google Sheets and WhatsApp") == "alternative"
    assert engine._classify_memory_type("objections", "Why would you hesitate?", "I doubt the food quality after midnight") == "objection"
    assert engine._classify_memory_type("trust_verification", "Is it safe?", "I need verified secure payment processing") == "trust"
    assert engine._classify_memory_type("purchase_decision", "Will you switch?", "I will switch only if pricing is transparent") == "switching_reason"

