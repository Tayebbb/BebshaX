"""Unit tests for Structured Research Planner."""

import pytest
from bebshax.research.planner import (
    generate_structured_research_plan,
    get_deterministic_research_plan,
)


@pytest.mark.asyncio
async def test_deterministic_research_plan_food_idea():
    idea = "I want to build an AI-powered meal planning app for university students in Bangladesh."
    plan = get_deterministic_research_plan(idea)

    assert "meal" in plan.business_idea.lower() or "food" in plan.business_idea.lower()
    assert len(plan.target_market) >= 2
    assert any("student" in tm.lower() for tm in plan.target_market)
    assert len(plan.problem_areas) >= 3
    assert len(plan.behavioral_questions) >= 2
    assert len(plan.economic_questions) >= 2
    assert len(plan.dataset_requirements) >= 2

    # Verify dataset requirements structure
    categories = [r.category for r in plan.dataset_requirements]
    assert "food_spending" in categories or "food_consumption" in categories


@pytest.mark.asyncio
async def test_deterministic_research_plan_b2b_saas():
    idea = "Automated POS and accounting software for small restaurants and cafes in Dhaka"
    plan = get_deterministic_research_plan(idea)

    assert len(plan.target_market) >= 2
    assert any("restaurant" in tm.lower() or "sme" in tm.lower() for tm in plan.target_market)
    assert len(plan.dataset_requirements) >= 1
    assert any(r.category == "sme_operations" for r in plan.dataset_requirements)


@pytest.mark.asyncio
async def test_deterministic_research_plan_edtech():
    idea = "AI diagnostic test preparation platform for BCS and University Admission examinees"
    plan = get_deterministic_research_plan(idea)

    assert len(plan.target_market) >= 2
    assert len(plan.economic_questions) >= 2
    assert any("education" in r.category for r in plan.dataset_requirements)


@pytest.mark.asyncio
async def test_generate_structured_research_plan_without_llm():
    idea = "Sustainable bamboo fashion marketplace with cash on delivery in Bangladesh"
    plan = await generate_structured_research_plan(idea)

    assert plan.business_idea == idea
    assert len(plan.target_market) >= 1
    assert len(plan.dataset_requirements) >= 1
    assert plan.summary is not None
