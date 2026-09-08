"""Unit tests for the Structured Research Planner.

The planner writes nothing itself: the plan is the model's analysis of THIS idea
(with the study text passed as untrusted data) and every failure is explicit —
there is no keyword-bucket template plan and no regional default.
"""

import json

import pytest

from bebshax.research.planner import (
    RESEARCH_PLAN_FAILED,
    DatasetRequirementSpec,
    generate_structured_research_plan,
)
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput


class _StubLLM:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]

        class _R:
            provider = "fake"
            model = "stub"

        r = _R()
        r.text = text
        return r


def _plan_json(**overrides):
    base = {
        "business_idea": "x",
        "target_market": ["Independent café owners in Lisbon"],
        "problem_areas": ["Manual stock counts", "Cash reconciliation errors"],
        "behavioral_questions": ["How often is stock counted?"],
        "economic_questions": ["What is the monthly software budget?"],
        "competition_questions": ["Which POS tools are used today?"],
        "market_questions": ["How many cafés operate in Lisbon?"],
        "dataset_requirements": [
            {
                "category": "sme_operations",
                "description": "turnover and costs",
                "target_variables": ["monthly_turnover"],
                "geographic_scope": "Lisbon, Portugal",
                "population_scope": "independent cafés",
            }
        ],
        "summary": "Validate POS demand among Lisbon cafés.",
    }
    base.update(overrides)
    return json.dumps(base)


@pytest.mark.asyncio
async def test_plan_is_model_written_and_region_comes_from_the_brief():
    idea = "Automated POS and accounting software for small cafés in Lisbon"
    stub = _StubLLM(_plan_json())
    plan = await generate_structured_research_plan(idea, target_audience="café owners", llm_service=stub)

    assert plan.business_idea == idea
    assert plan.source == "llm" and plan.served_by == "fake/stub"
    assert plan.fallback_reason is None
    assert plan.dataset_requirements[0].geographic_scope == "Lisbon, Portugal"
    # The brief travels as untrusted data; the model is told to infer geography.
    prompt = stub.requests[0].messages[0].content
    assert "RESEARCH_BRIEF" in prompt and idea in prompt and "café owners" in prompt
    assert "never assume one" in prompt
    assert "Bangladesh" not in prompt


def test_dataset_requirement_has_no_regional_default():
    spec = DatasetRequirementSpec(category="c", description="d")
    assert spec.geographic_scope == "" and spec.population_scope == ""


@pytest.mark.asyncio
async def test_without_llm_planning_fails_explicitly():
    with pytest.raises(LLMUnavailable) as info:
        await generate_structured_research_plan("Sustainable bamboo fashion marketplace")
    assert info.value.status_code == 503 and info.value.error_code == "llm_unavailable"


@pytest.mark.asyncio
async def test_unusable_reply_is_retried_once_then_fails_explicitly():
    stub = _StubLLM("not json at all")
    with pytest.raises(UnusableModelOutput) as info:
        await generate_structured_research_plan("idea", llm_service=stub)
    assert len(stub.requests) == 2
    assert info.value.error_code == RESEARCH_PLAN_FAILED
    assert info.value.extra["attempts"] == 2


@pytest.mark.asyncio
async def test_incomplete_reply_then_good_reply_marks_the_retry():
    stub = _StubLLM(json.dumps({"target_market": [], "problem_areas": []}), _plan_json())
    plan = await generate_structured_research_plan("idea", llm_service=stub)
    assert len(stub.requests) == 2
    assert plan.fallback_reason == "retried_after_unparseable_reply"
    assert plan.target_market == ["Independent café owners in Lisbon"]
