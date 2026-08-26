"""
Tests for Advanced Persona Generation, Dynamic Domain Adaptation, Constraints, Contradiction Detection & Decision Tracking.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, MarketSegments, Personas, Studies
from bebshax.interview.engine import InterviewEngine
from bebshax.personas.generator import (
    detect_study_domain,
    generate_domain_specific_profile,
    _generate_deterministic_persona_fallback,
    calculate_segment_quotas,
)


class DummySegment:
    def __init__(self, id: str, name: str, pct: float, min_b: int = 300, max_b: int = 600):
        self.id = id
        self.name = name
        self.population_percentage = pct
        self.characteristics = {
            "demographics": {"age_range": [20, 30], "dominant_occupation": "Nurse / Night Worker"},
            "economics": {"monthly_budget": {"min": min_b, "max": max_b, "median": (min_b + max_b) // 2}},
            "behavior": {"technology_familiarity": "Medium"},
            "needs": ["Reliable late night meal delivery"],
        }


def test_detect_study_domain():
    """Verify intelligent domain classification from study title, prompt and target audience."""
    # 1. Food Delivery
    food_ctx = {
        "title": "Night Shift Canteen Delivery",
        "prompt": "Late-night food delivery service for hospital workers in Dhaka",
        "target_audience": "Hospital nurses, doctors, shift workers",
        "pricing_hypothesis": "150-250 BDT per meal",
    }
    assert detect_study_domain(food_ctx) == "food_delivery"

    # 2. SaaS / Productivity
    saas_ctx = {
        "title": "InvoiceFlow B2B SaaS",
        "prompt": "Lightweight invoice reconciliation and spreadsheet automation tool",
        "target_audience": "Small business founders and financial analysts",
        "pricing_hypothesis": "500 BDT/month subscription",
    }
    assert detect_study_domain(saas_ctx) == "saas_productivity"

    # 3. Fitness / Health
    fitness_ctx = {
        "title": "HomeFit Bangladesh",
        "prompt": "Personalized home workout and diet guide app for busy professionals",
        "target_audience": "Corporate desk workers seeking health routines",
        "pricing_hypothesis": "300 BDT/month",
    }
    assert detect_study_domain(fitness_ctx) == "fitness_health"

    # 4. EdTech / Learning
    edtech_ctx = {
        "title": "BCS & Bank Prep Exam Hero",
        "prompt": "Affordable exam practice test and video syllabus guide for university students",
        "target_audience": "Final year university students preparing for BCS exams",
        "pricing_hypothesis": "250 BDT/month",
    }
    assert detect_study_domain(edtech_ctx) == "edtech_learning"


def test_generate_domain_specific_profile_food_delivery():
    """Verify food delivery business generates food_source, meal_timing, delivery_concerns."""
    domain_attrs, constraints, goals, needs, pains = generate_domain_specific_profile(
        domain="food_delivery", median_budget=450, index=0
    )
    assert "food_source" in domain_attrs
    assert "meal_timing" in domain_attrs
    assert "delivery_concerns" in domain_attrs
    assert "bKash" in domain_attrs["payment_method"]
    assert constraints["max_monthly_budget"] == 450
    assert constraints["subscription_tolerance"] == "Low"
    assert any("late-night" in g.lower() or "meal" in g.lower() for g in goals)


def test_generate_domain_specific_profile_saas_productivity():
    """Verify SaaS business generates current_tools, workflow, desired_features, switching_barrier."""
    domain_attrs, constraints, goals, needs, pains = generate_domain_specific_profile(
        domain="saas_productivity", median_budget=800, index=1
    )
    assert "current_tools" in domain_attrs
    assert "workflow" in domain_attrs
    assert "desired_features" in domain_attrs
    assert "switching_barrier" in domain_attrs
    assert constraints["max_monthly_budget"] == 800
    assert any("spreadsheet" in g.lower() or "software" in g.lower() or "invoicing" in g.lower() for g in goals)


def test_fallback_generates_rich_grounded_persona():
    """Verify deterministic fallback constructs complete persona with Big Five, domain attributes, and explicit constraints."""
    seg = DummySegment("seg_1", "Night Shift Ward Nurses", 60.0, min_b=350, max_b=700)
    ctx = {
        "title": "Hospital Late Night Food App",
        "prompt": "Safe late-night food deliveries for hospital personnel in Dhaka",
        "target_audience": "Nurses and night shift medical staff",
    }
    draft = _generate_deterministic_persona_fallback(seg, 0, ctx, [])
    assert draft.name == "Nusrat Jahan"
    assert draft.personality["conscientiousness"] == 86
    assert "domain_attributes" in draft.detailed_attributes
    assert draft.detailed_attributes["domain_attributes"]["food_source"] is not None
    assert draft.constraints["max_monthly_budget"] == 525
    assert draft.commercial_profile["monthly_budget_bdt"] == 525
    assert draft.status == "ready"


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
    assert "exceeds stated monthly budget of ৳400" in details
    assert "What changed your willingness to pay" in follow_up
    assert conf == 0.60

    # 2. Consistent response: declining out-of-budget proposal
    has_contra2, details2, follow_up2, conf2 = engine._detect_contradiction(
        mock_persona,
        question="Would you pay ৳2,500 every month for unlimited priority orders?",
        reply="No, ৳2,500 is completely out of my monthly allowance. My maximum food app budget is around ৳400.",
    )
    assert has_contra2 is False
    assert details2 is None
    assert conf2 == 0.90


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

