"""Tests for BehavioralSimulationEngine: multi-type simulation, context assembly, anti-sycophancy, and synthesis."""

import json
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bebshax.behavioral.engine import BehavioralSimulationEngine
from bebshax.behavioral.orm import (
    BehavioralInsights,
    BehavioralTestResults,
    BehavioralTestRuns,
    BehavioralTestScenarios,
    BehavioralTests,
)
from bebshax.db.models import Businesses, EvidenceClaims, MarketSegments, Personas, Studies
from bebshax.interview.orm import InterviewInsights
from bebshax.llm import LLMRequest, LLMResult, LLMService, ProvenanceRecord, TaskType


class FakeBehavioralLLM(LLMService):
    def __init__(self, response_text: str | None = None):
        self.calls: list[LLMRequest] = []
        self.response_text = response_text or json.dumps({
            "decision": "unlikely_to_buy",
            "decision_label": "Unlikely to Buy",
            "probability": 0.32,
            "key_factors": [
                {
                    "name": "Price Sensitivity",
                    "impact": "high",
                    "direction": "negative",
                    "description": "Monthly fee of ৳299 exceeds typical allocation of ৳150-200 for digital tools."
                }
            ],
            "motivators": ["Time saving potential"],
            "objections": ["Recurring price exceeds disposable budget"],
            "reasoning_summary": "The persona finds ৳299/month too high given their modest student budget."
        })

    async def complete(self, req: LLMRequest) -> LLMResult:
        self.calls.append(req)
        return LLMResult(
            text=self.response_text,
            provider="fake",
            model="fake-model",
            provenance=ProvenanceRecord(
                request_id=req.request_id,
                task=req.task,
                served_by_provider="fake",
                response_model="fake-model",
                success=True,
            ),
        )


@pytest.mark.asyncio
async def test_simulate_persona_pricing_grounding(session_maker: sessionmaker[AsyncSession]):
    fake_llm = FakeBehavioralLLM()
    engine = BehavioralSimulationEngine(fake_llm, session_maker)

    async with session_maker() as session:
        # Create study
        study = Studies(id="std_behav_1", title="Student AI Meal App", prompt="Meal planner for students")
        session.add(study)

        # Create persona with BDT budget and interview insight
        persona = Personas(
            id="p_behav_1",
            study_id="std_behav_1",
            owner_id="usr_system_holder",
            name="Nadia Rahman",
            demographics={"age": "22", "occupation": "University Student", "income_level": "Modest (৳4000/mo allowance)"},
            commercial_profile={"monthly_budget_bdt": "400", "payment_method": "bKash"},
            bio="Dhaka university student living in hostel.",
            pain_points=["Spending 1 hour daily deciding what to cook", "Tight budget"],
            motivations=["Save exam preparation time", "Low cost meals"],
        )
        session.add(persona)

        # Add Part 6 interview insight
        insight = InterviewInsights(
            id="ins_behav_1",
            interview_id="conv_1",
            study_id="std_behav_1",
            persona_id="p_behav_1",
            type="pricing",
            title="Price threshold at ৳150",
            description="Persona stated any subscription over ৳150 feels too high.",
            supporting_turn_numbers=[3, 5],
            confidence=0.90,
        )
        session.add(insight)

        # Add Part 2 evidence claim
        claim = EvidenceClaims(
            id="claim_behav_1",
            study_id="std_behav_1",
            claim_text="74% of university students in Dhaka have discretionary budget under ৳500/month.",
            status="supported",
            category="pricing",
            confidence=0.88,
        )
        session.add(claim)
        await session.commit()

        # Run pricing test simulation
        result = await engine.simulate_persona_response(
            persona=persona,
            study=study,
            test_type="pricing_test",
            scenario_title="Standard Monthly Tier",
            scenario_text="App provides automated meal plans and grocery lists for ৳299/month.",
            parameters={"price": "৳299", "billing_period": "monthly", "alternative": "Free YouTube recipes"},
            session=session,
        )

        assert result["persona_id"] == "p_behav_1"
        assert result["persona_name"] == "Nadia Rahman"
        assert result["decision"] == "unlikely_to_buy"
        assert result["probability"] == 0.32
        assert result["confidence"] in ("medium", "high")
        assert len(result["key_factors"]) >= 1
        assert "Price Sensitivity" in [f["name"] for f in result["key_factors"]]
        assert len(result["objections"]) >= 1
        assert result["simulation_context_sources"]["persona_profile"] is True
        assert result["simulation_context_sources"]["interview_insights"] is True
        assert result["simulation_context_sources"]["research_evidence"] is True

        # Verify governed LLM request
        assert len(fake_llm.calls) == 1
        req = fake_llm.calls[0]
        assert req.task == TaskType.BEHAVIORAL_SIMULATION
        user_msg = req.messages[1].content
        assert "Nadia Rahman" in user_msg
        assert "Price threshold at ৳150" in user_msg
        assert "74% of university students" in user_msg
        assert "৳299" in user_msg


@pytest.mark.asyncio
async def test_compute_aggregate_synthesis(session_maker: sessionmaker[AsyncSession]):
    fake_llm = FakeBehavioralLLM()
    engine = BehavioralSimulationEngine(fake_llm, session_maker)

    results = [
        {
            "persona_id": "p1",
            "decision": "unlikely_to_buy",
            "probability": 0.30,
            "confidence": "high",
            "segment_id": "seg_budget",
            "motivators": ["Time saving"],
            "objections": ["Price too high", "Free alternatives suffice"],
            "key_factors": [{"name": "Price Sensitivity", "impact": "high"}],
        },
        {
            "persona_id": "p2",
            "decision": "would_not_buy",
            "probability": 0.20,
            "confidence": "high",
            "segment_id": "seg_budget",
            "motivators": ["Quick planning"],
            "objections": ["Price too high"],
            "key_factors": [{"name": "Price Sensitivity", "impact": "high"}],
        },
        {
            "persona_id": "p3",
            "decision": "likely_to_buy",
            "probability": 0.78,
            "confidence": "medium",
            "segment_id": "seg_time",
            "motivators": ["Time saving", "Nutrition tracking"],
            "objections": ["Onboarding effort"],
            "key_factors": [{"name": "Convenience", "impact": "high"}],
        },
    ]

    segments_map = {
        "seg_budget": "Budget-Conscious Students",
        "seg_time": "Time-Constrained Students",
    }

    (
        metrics,
        segment_analysis,
        cross_patterns,
        risks,
        opportunities,
        insights,
    ) = engine.compute_aggregate_synthesis(results, segments_map, "pricing_test")

    assert metrics["total_personas"] == 3
    assert metrics["positive_count"] == 1
    assert metrics["negative_count"] == 2
    assert metrics["neutral_count"] == 0
    assert metrics["positive_percentage"] == 33.3
    assert metrics["negative_percentage"] == 66.7
    assert metrics["average_likelihood"] == 0.43

    assert len(segment_analysis) == 2
    budget_seg = next(s for s in segment_analysis if s["segment_id"] == "seg_budget")
    time_seg = next(s for s in segment_analysis if s["segment_id"] == "seg_time")

    assert budget_seg["negative_percentage"] == 100.0
    assert budget_seg["average_likelihood"] == 0.25
    assert budget_seg["top_objection"] == "Price too high"

    assert time_seg["positive_percentage"] == 100.0
    assert time_seg["average_likelihood"] == 0.78

    assert "Price too high" in cross_patterns["top_objections"]
    assert "Time saving" in cross_patterns["top_motivators"]

    # Risk should be flagged because negative% >= 40%
    assert len(risks) >= 1
    assert "High Resistance" in risks[0]["title"]

    # Segment divergence insight should be flagged
    assert any(i["type"] == "segment_difference" for i in insights)


@pytest.mark.asyncio
async def test_full_test_run_execution(session_maker: sessionmaker[AsyncSession]):
    fake_llm = FakeBehavioralLLM()
    engine = BehavioralSimulationEngine(fake_llm, session_maker)

    async with session_maker() as session:
        study = Studies(id="std_behav_run", title="Study Run Test", prompt="Food App")
        session.add(study)

        p1 = Personas(id="p_run_1", study_id="std_behav_run", owner_id="usr_system_holder", name="Tanvir Ahmed", commercial_profile={"monthly_budget_bdt": "600"})
        p2 = Personas(id="p_run_2", study_id="std_behav_run", owner_id="usr_system_holder", name="Sadia Islam", commercial_profile={"monthly_budget_bdt": "300"})
        session.add_all([p1, p2])

        test = BehavioralTests(
            id="bt_run_1",
            study_id="std_behav_run",
            name="Feature Test: Weekly Meal Plan",
            test_type="feature_test",
            configuration={"feature": "AI Weekly Meal Planner", "benefit": "30 mins saved"},
        )
        session.add(test)

        run = BehavioralTestRuns(
            id="btr_run_1",
            behavioral_test_id="bt_run_1",
            study_id="std_behav_run",
            scenario_snapshot={"title": "Weekly Meal Plan", "structured_parameters": {"feature": "AI Weekly Planner"}},
            target_population_type="all",
            target_persona_ids=["p_run_1", "p_run_2"],
            status="pending",
        )
        session.add(run)
        await session.commit()

        # Execute run
        completed_run = await engine.execute_test_run(run_id="btr_run_1")

        assert completed_run.status == "completed"
        assert completed_run.persona_count == 2
        assert completed_run.completed_count == 2
        assert completed_run.failed_count == 0
        assert completed_run.aggregate_metrics["total_personas"] == 2

        # Check DB results
        res_results = await session.execute(
            select(BehavioralTestResults).where(BehavioralTestResults.test_run_id == "btr_run_1")
        )
        db_results = res_results.scalars().all()
        assert len(db_results) == 2
        assert {r.persona_id for r in db_results} == {"p_run_1", "p_run_2"}
