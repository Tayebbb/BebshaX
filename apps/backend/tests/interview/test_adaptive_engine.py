import pytest
from sqlalchemy import select

from bebshax.db.models import Businesses, MarketSegments, Personas, Studies
from bebshax.interview.engine import InterviewEngine, InterviewFinished
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm import TaskType


@pytest.fixture
async def full_study_context(session_maker):
    async with session_maker() as session:
        study = Studies(
            id="std_meal_prep",
            user_id="usr_tester",
            title="Student Meal Planning App",
            goal="demand_validation",
            prompt="Affordable meal prep app for university students in Bangladesh",
            target_audience="Dhaka University students living in dorms/messes",
            pricing_hypothesis="Subscription under 300 BDT/month",
            status="in_progress",
        )
        session.add(study)

        segment = MarketSegments(
            id="seg_budget_students",
            study_id="std_meal_prep",
            segmentation_run_id="seg_run_1",
            name="Budget-Conscious Students",
            description="Students with strict monthly stipends seeking fast, affordable dining.",
            characteristics={"meal_budget_daily": "100-150 BDT", "dining_style": "mess/delivery"},
        )
        session.add(segment)

        persona = Personas(
            id="per_nadia",
            study_id="std_meal_prep",
            user_id="usr_tester",
            owner_id="usr_tester",
            segment_id="seg_budget_students",
            name="Nadia Rahman",
            version=1,
            demographics={
                "age": 21,
                "occupation": "University Student",
                "location": "Dhanmondi, Dhaka",
                "education": "Undergraduate BBA",
                "income_level": "৳6,000 monthly allowance",
            },
            bio="Third year student balancing exam prep and messy kitchen access in student hostel.",
            quote="I just want healthy food without spending half my monthly allowance.",
            goals=["Save time during exam weeks", "Stay within ৳400/month food app budget"],
            pain_points=["Mess food is repetitive", "Meal delivery delivery fees are too high"],
            objections=["Will cancel if monthly fee is over ৳400 BDT"],
            behaviors=["Uses bKash for all payments", "Orders lunch via phone on busy days"],
            commercial_profile={
                "monthly_budget_bdt": 400,
                "price_sensitivity": "Very High",
                "payment_preference": "bKash",
            },
            technology_profile={"primary_devices": ["Android smartphone"]},
            evidence_citations=[
                {"claim": "72% of university hostellers spend under 150 BDT on lunch", "source": "BBS Student Living Survey"}
            ],
            grounding_score=0.92,
        )
        session.add(persona)
        await session.commit()
    return "std_meal_prep", "per_nadia"


async def test_adaptive_interview_grounded_composition(
    session_maker, full_study_context, memory_service, llm_factory
):
    study_id, persona_id = full_study_context
    llm, adapter = llm_factory([
        "Hi! Yes, I struggle to balance meal planning with my studies at IBA.",
        "Honestly, ৳2,000 a month is way outside my budget. My whole monthly meal allowance is only around ৳6,000!",
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)

    # 1. Start interview
    interview = await engine.start(
        persona_id=persona_id,
        objective="Pricing & Pain Point Exploration",
        study_id=study_id,
        custom_objective="Test willingness to pay for subscription",
        length_tier="short",
    )
    assert interview.status == "active"
    assert interview.max_turns == 6
    assert interview.length_tier == "short"

    # 2. First question
    res1 = await engine.ask(interview.id, "How do you currently handle meals during exams?")
    assert "Hi!" in res1["reply"]
    assert res1["turn_number"] == 2
    assert res1["topic"] in ("current_behavior", "pain_points", "general")

    # Verify that the system prompt contained the rich persona identity card, commercial budget, and study context
    req1 = adapter.requests[0]
    sys_content = req1.messages[0].content
    assert "Nadia Rahman" in sys_content
    assert "Dhanmondi, Dhaka" in sys_content
    assert "Monthly discretionary budget ৳400 BDT" in sys_content
    assert "Budget-Conscious Students" in sys_content
    assert "Pricing & Pain Point Exploration" in sys_content
    assert "BBS Student Living Survey" in sys_content

    # 3. Second question testing anti-sycophantic response
    res2 = await engine.ask(interview.id, "Would you pay ৳2,000 per month for our premium meal AI?")
    assert "2,000" in res2["reply"]
    assert res2["turn_number"] == 4
    assert res2["topics_explored"].get("pricing_budget") == "explored"

    # 4. Check transcript
    conv, turns = await engine.transcript(interview.id)
    assert len(turns) == 4
    assert [t.role for t in turns] == ["interviewer", "persona", "interviewer", "persona"]


async def test_interview_length_limit_and_completion_synthesis(
    session_maker, full_study_context, memory_service, llm_factory
):
    study_id, persona_id = full_study_context
    synthesis_json = """{
      "summary": "Nadia needs affordable meal scheduling that stays strictly below 400 BDT/month due to tight hostel budget.",
      "key_findings": [
        "Price sensitivity is extreme; 2000 BDT proposal was immediately rejected.",
        "Relies primarily on bKash mobile payments.",
        "Exam periods create severe meal planning friction."
      ],
      "insights": [
        {
          "type": "pricing",
          "title": "Strict ceiling at 400 BDT/month",
          "description": "The persona cannot afford luxury subscriptions on a student allowance.",
          "supporting_turn_numbers": [2, 4],
          "confidence": 0.95
        },
        {
          "type": "pain_point",
          "title": "Repetitive dining during exam prep",
          "description": "Friction peaks when dorm facilities are closed or crowded.",
          "supporting_turn_numbers": [2],
          "confidence": 0.88
        }
      ]
    }"""
    llm, adapter = llm_factory([
        "I find mess food very monotonous.",
        "I pay with bKash every day.",
        synthesis_json,
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)

    interview = await engine.start(
        persona_id=persona_id,
        objective="Pain Point Discovery",
        study_id=study_id,
        length_tier="short",
    )

    await engine.ask(interview.id, "What's the hardest part about hostel dining?")
    await engine.ask(interview.id, "How do you pay for groceries?")

    # Complete the interview
    synthesis = await engine.complete(interview.id)
    assert synthesis["status"] == "completed"
    assert "400 BDT" in synthesis["summary"]
    assert len(synthesis["key_findings"]) == 3
    assert len(synthesis["structured_insights"]) == 2

    # Verify insights were stored in database
    async with session_maker() as session:
        insights = list(
            (await session.execute(
                select(InterviewInsights).where(InterviewInsights.interview_id == interview.id)
            )).scalars()
        )
        assert len(insights) == 2
        assert insights[0].type in ("pricing", "pain_point")
        assert insights[0].supporting_turn_numbers in ([2, 4], [2])
        assert insights[0].is_synthetic is True

    # Attempting to ask in a completed interview raises InterviewFinished
    with pytest.raises(InterviewFinished):
        await engine.ask(interview.id, "One more question!")


async def test_failed_synthesis_falls_back_honestly(
    session_maker, memory_service, llm_factory, full_study_context
):
    """When insight synthesis returns unparseable output, the fallback must be
    labeled mechanical with confidence 0.0 — never dressed up as analysis
    with an invented confidence (M-series honesty)."""
    study_id, persona_id = full_study_context
    llm, adapter = llm_factory([
        "The mess food is quite repetitive honestly.",
        "THIS IS NOT JSON AT ALL — synthesis reply that cannot parse",
    ])
    engine = InterviewEngine(llm, session_maker, memory=memory_service)
    interview = await engine.start(
        persona_id=persona_id,
        objective="Pain Point Discovery",
        study_id=study_id,
        length_tier="short",
    )
    await engine.ask(interview.id, "What's the hardest part about hostel dining?")

    synthesis = await engine.complete(interview.id)
    assert synthesis["status"] == "completed"
    assert synthesis["summary"].startswith("Automated synthesis unavailable")
    [insight] = synthesis["structured_insights"]
    assert insight["title"] == "Unanalyzed excerpt (synthesis unavailable)"
    assert insight["confidence"] == 0.0

    async with session_maker() as session:
        rows = list(
            (await session.execute(
                select(InterviewInsights).where(InterviewInsights.interview_id == interview.id)
            )).scalars()
        )
        assert len(rows) == 1
        assert rows[0].confidence == 0.0  # persisted, not the ORM default
