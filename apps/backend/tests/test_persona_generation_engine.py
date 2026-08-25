"""Unit and integration tests for synthetic persona generation engine and validator."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, MarketSegments, PersonaGenerationRuns, Personas, Studies, _utcnow
from bebshax.personas.generator import calculate_segment_quotas, generate_personas_for_study
from bebshax.personas.service import PersonaGenerationService
from bebshax.personas.validator import validate_synthetic_persona


class MockSegment:
    def __init__(self, id: str, name: str, pct: float, min_age: int = 18, max_age: int = 24, min_b: int = 250, max_b: int = 600):
        self.id = id
        self.name = name
        self.population_percentage = pct
        self.characteristics = {
            "demographics": {"age_range": [min_age, max_age], "dominant_occupation": "Student"},
            "economics": {"monthly_budget": {"min": min_b, "max": max_b, "median": (min_b + max_b) // 2}},
            "behavior": {"study_hours_per_day": 4.0, "technology_familiarity": "High"},
            "needs": ["Affordable micro-billing"],
        }


def test_calculate_segment_quotas_equal():
    segments = [
        MockSegment("seg_1", "Segment 1", 50.0),
        MockSegment("seg_2", "Segment 2", 30.0),
        MockSegment("seg_3", "Segment 3", 20.0),
    ]
    quotas = calculate_segment_quotas(segments, target_count=6, strategy="equal")
    assert quotas == {"seg_1": 2, "seg_2": 2, "seg_3": 2}


def test_calculate_segment_quotas_population_weighted():
    segments = [
        MockSegment("seg_1", "Primary Segment", 60.0),
        MockSegment("seg_2", "Secondary Segment", 30.0),
        MockSegment("seg_3", "Niche Segment", 10.0),
    ]
    quotas = calculate_segment_quotas(segments, target_count=10, strategy="population_weighted")
    # Total must equal 10 and each segment has at least 1
    assert sum(quotas.values()) == 10
    assert quotas["seg_1"] >= quotas["seg_2"] >= quotas["seg_3"]
    assert quotas["seg_3"] >= 1


def test_validate_synthetic_persona_valid():
    seg_char = {
        "demographics": {"age_range": [19, 23]},
        "economics": {"monthly_budget": {"min": 300, "max": 600, "median": 450}},
    }
    persona = {
        "name": "Nadia Rahman",
        "demographics": {"age": 21, "occupation": "Student", "location": "Dhaka"},
        "goals": ["Ace semester finals"],
        "needs": ["Fast timetable sync"],
        "pain_points": ["Expensive subscriptions"],
        "behaviors": ["Daily mobile user"],
        "commercial_profile": {"monthly_budget_bdt": 400},
        "evidence_citations": [{"claim_id": "clm_1"}],
    }
    outcome = validate_synthetic_persona(persona, seg_char)
    assert outcome.is_valid is True
    assert outcome.status == "ready"
    assert outcome.grounding_score >= 0.85
    assert len(outcome.warnings) == 0


def test_validate_synthetic_persona_out_of_bounds_warnings():
    seg_char = {
        "demographics": {"age_range": [18, 22]},
        "economics": {"monthly_budget": {"min": 250, "max": 500}},
    }
    persona = {
        "name": "X",  # too short
        "demographics": {"age": 45},  # way out of range
        "goals": [],  # missing
        "needs": [],  # missing
        "pain_points": [],  # missing
        "commercial_profile": {"monthly_budget_bdt": 15000},  # way above
    }
    outcome = validate_synthetic_persona(persona, seg_char)
    assert outcome.is_valid is False
    assert outcome.status == "needs_review"
    assert len(outcome.warnings) >= 3
    assert outcome.grounding_score < 0.80


@pytest.mark.asyncio
async def test_generate_personas_for_study_fallback():
    segments = [
        MockSegment("seg_1", "Budget Students", 65.0),
        MockSegment("seg_2", "Ambitious Preppers", 35.0),
    ]
    mock_study = MagicMock()
    mock_study.title = "Exam Prep Platform"
    mock_study.prompt = "Affordable study planning"
    mock_study.target_audience = "College students"
    mock_study.pricing_hypothesis = "৳300/month"

    drafts = await generate_personas_for_study(
        study=mock_study,
        segments=segments,
        target_count=4,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=None,
    )

    assert len(drafts) == 4
    for d in drafts:
        assert len(d.name) > 2
        assert d.status in ("ready", "needs_review")
        assert d.grounding_score >= 0.80
        assert len(d.goals) >= 1
        assert len(d.pain_points) >= 1
        assert "monthly_budget_bdt" in d.commercial_profile


@pytest.mark.asyncio
async def test_persona_generation_service_lifecycle():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        # Setup test study and market segment
        study = Studies(
            id="std_persona_lifecycle_test",
            title="Persona Service Test Study",
            status="active",
            step=2,
        )
        session.add(study)

        segment = MarketSegments(
            id="seg_lifecycle_1",
            study_id=study.id,
            segmentation_run_id="srun_test_1",
            name="Tech-Savvy Undergrads",
            cluster_label="cluster_0",
            description="Active smartphone users preparing for exams",
            population_count=120,
            population_percentage=60.0,
            characteristics={
                "demographics": {"age_range": [19, 23], "dominant_occupation": "Undergrad"},
                "economics": {"monthly_budget": {"min": 300, "max": 600, "median": 450}},
                "behavior": {"technology_familiarity": "High"},
            },
        )
        session.add(segment)
        await session.commit()

        service = PersonaGenerationService(session)

        # 1. Run generation
        run, personas = await service.create_generation_run(
            study_id=study.id,
            target_count=3,
            distribution_strategy="equal",
        )

        assert run.status == "completed"
        assert run.generated_count == 3
        assert len(personas) == 3

        # 2. List personas
        listed = await service.list_personas(study_id=study.id)
        assert len(listed) == 3

        # 3. Get individual persona
        single = await service.get_persona(study_id=study.id, persona_id=personas[0].id)
        assert single is not None
        assert single.name == personas[0].name

        # 4. Regenerate persona
        regen = await service.regenerate_persona(study_id=study.id, persona_id=personas[0].id)
        assert regen.version == 2

        # 5. List runs and delete
        runs = await service.list_runs(study_id=study.id)
        assert len(runs) == 1
        deleted = await service.delete_run(study_id=study.id, run_id=run.id)
        assert deleted is True

        personas_after_del = await service.list_personas(study_id=study.id)
        assert len(personas_after_del) == 0
