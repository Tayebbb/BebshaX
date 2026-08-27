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
    # No claim provenance supplied → grounding is honestly zero, never a bonus.
    assert outcome.grounding_score == 0.0
    assert outcome.confidence == 0.0
    assert len(outcome.warnings) == 0


def test_grounding_score_is_measured_from_claim_provenance():
    """grounding = OBSERVED/total; confidence = (OBSERVED+INFERRED)/total."""
    persona = {
        "name": "Nadia Rahman",
        "demographics": {"age": 21},
        "goals": ["g1", "g2"],
        "needs": ["n1"],
        "pain_points": ["p1"],
        "commercial_profile": {},
        "claim_provenance": {
            "goals": [
                {"value": "g1", "provenance": "OBSERVED", "evidence_ids": ["clm_1"]},
                {"value": "g2", "provenance": "OBSERVED", "evidence_ids": ["clm_2"]},
            ],
            "needs": [{"value": "n1", "provenance": "INFERRED", "evidence_ids": []}],
            "pain_points": [{"value": "p1", "provenance": "SYNTHETIC", "evidence_ids": []}],
        },
    }
    outcome = validate_synthetic_persona(persona, {})
    assert outcome.grounding_score == 0.5  # 2 OBSERVED of 4 claims
    assert outcome.confidence == 0.75  # 3 non-synthetic of 4 claims


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
    assert outcome.grounding_score == 0.0


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
        # Template drafts invent every claim (all SYNTHETIC) — grounding must
        # be honestly zero and citations honestly empty, never decorated.
        assert d.grounding_score == 0.0
        assert d.evidence_citations == []
        assert len(d.goals) >= 1
        assert len(d.pain_points) >= 1
        assert "monthly_budget_bdt" in d.commercial_profile
        # template drafts carry their honest origin label
        assert d.generation_model == "deterministic-template-fallback"


class _FakeLLM:
    """Minimal llm_service stub: returns a fixed reply with provenance."""

    def __init__(self, text: str, provider: str = "fake", model: str = "m9") -> None:
        self._text = text
        self._provider = provider
        self._model = model

    async def complete(self, request):
        from types import SimpleNamespace

        return SimpleNamespace(
            text=self._text,
            provenance=SimpleNamespace(
                served_by_provider=self._provider, served_by_model=self._model
            ),
        )


def _study_mock():
    mock_study = MagicMock()
    mock_study.title = "Exam Prep Platform"
    mock_study.prompt = "Affordable study planning"
    mock_study.target_audience = "College students"
    mock_study.pricing_hypothesis = "৳300/month"
    return mock_study


@pytest.mark.asyncio
async def test_llm_drafts_are_stamped_with_the_real_serving_model():
    import json as _json

    reply = _json.dumps(
        {
            "personas": [
                {
                    "name": "Tania Rahman",
                    "age": 22,
                    "occupation": "Student",
                    "location": "Dhaka",
                    "monthly_budget_bdt": 350,
                    "goals": ["pass exams"],
                    "pain_points": ["expensive coaching"],
                }
            ]
        }
    )
    drafts = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=1,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_FakeLLM(reply, provider="ollama", model="llama3.2:3b"),
    )
    assert len(drafts) == 1
    # provenance-derived origin — never the old fabricated "qwen3.5-grounded"
    assert drafts[0].generation_model == "ollama/llama3.2:3b"


@pytest.mark.asyncio
async def test_malformed_llm_output_falls_back_to_labeled_templates():
    drafts = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=2,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_FakeLLM("this is not json at all"),
    )
    assert len(drafts) == 2
    assert all(d.generation_model == "deterministic-template-fallback" for d in drafts)


@pytest.mark.asyncio
async def test_claim_provenance_is_verified_and_downgrade_only():
    """Cited ids are checked against the claims actually shown; nothing upgrades."""
    import json as _json
    from types import SimpleNamespace

    claim = SimpleNamespace(
        id="ev_1", claim_text="Students cap spending at ৳400/mo", category="economics", confidence=0.9
    )
    reply = _json.dumps(
        {
            "personas": [
                {
                    "name": "Tania Rahman",
                    "age": 22,
                    "occupation": "Student",
                    "location": "Dhaka",
                    "monthly_budget_bdt": 350,
                    "goals": [
                        {"value": "stay under ৳400/mo", "provenance": "OBSERVED", "evidence_ids": ["c1"]},
                        {"value": "fabricated citation", "provenance": "OBSERVED", "evidence_ids": ["C9"]},
                        "plain legacy string",
                    ],
                    "needs": [{"value": "flexible billing", "provenance": "INFERRED", "evidence_ids": []}],
                    "pain_points": [{"value": "mystery label", "provenance": "banana", "evidence_ids": []}],
                }
            ]
        }
    )
    drafts = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=1,
        distribution_strategy="equal",
        evidence_claims=[claim],
        llm_service=_FakeLLM(reply),
    )
    assert len(drafts) == 1
    d = drafts[0]
    # ORM-facing fields stay plain strings, in model order
    assert d.goals == ["stay under ৳400/mo", "fabricated citation", "plain legacy string"]
    prov = d.detailed_attributes["claim_provenance"]
    g0, g1, g2 = prov["goals"]
    # lowercase cited alias "c1" matches case-insensitively and resolves to
    # the REAL evidence id — auditable after generation
    assert g0 == {"value": "stay under ৳400/mo", "provenance": "OBSERVED", "evidence_ids": ["ev_1"]}
    # C9 was never shown → citation stripped, OBSERVED downgraded to INFERRED
    assert g1 == {"value": "fabricated citation", "provenance": "INFERRED", "evidence_ids": []}
    # bare strings are unclassified invention
    assert g2 == {"value": "plain legacy string", "provenance": "SYNTHETIC", "evidence_ids": []}
    assert prov["needs"][0]["provenance"] == "INFERRED"
    assert prov["pain_points"][0]["provenance"] == "SYNTHETIC"  # unknown label


@pytest.mark.asyncio
async def test_template_fallback_claims_are_all_synthetic():
    drafts = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=2,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=None,
    )
    for d in drafts:
        prov = d.detailed_attributes["claim_provenance"]
        for group in ("goals", "needs", "pain_points"):
            assert prov[group], f"{group} classes missing"
            assert all(c["provenance"] == "SYNTHETIC" and c["evidence_ids"] == [] for c in prov[group])


@pytest.mark.asyncio
async def test_large_quota_is_sub_batched_and_never_template_ized():
    """A 6-persona single-segment quota must split into ≤3-persona requests
    (one whole-segment request exceeds the output budget and would fail or
    silently template-ize the segment — critic finding)."""
    import json as _json

    calls: list[int] = []

    class _BatchLLM:
        async def complete(self, request):
            from types import SimpleNamespace

            payload = _json.loads(request.messages[-1].content)
            n = payload["count_to_generate"]
            calls.append(n)
            assert request.max_output_tokens <= 4000
            personas = [
                {
                    "name": f"Persona {len(calls)}-{i}",
                    "age": 25 + i,
                    "occupation": "Student",
                    "location": "Dhaka",
                    "monthly_budget_bdt": 400,
                    "goals": ["study"],
                    "pain_points": ["cost"],
                }
                for i in range(n)
            ]
            return SimpleNamespace(
                text=_json.dumps({"personas": personas}),
                provenance=SimpleNamespace(served_by_provider="fake", served_by_model="m1"),
            )

    drafts = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=6,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_BatchLLM(),
    )
    assert len(drafts) == 6
    assert calls == [3, 3]  # sub-batched, never one 6-persona request
    assert all(d.generation_model == "fake/m1" for d in drafts)  # zero templates


@pytest.mark.asyncio
async def test_infrastructure_failures_propagate_not_masquerade():
    """AllCandidatesFailed must surface honestly — never silently replaced
    with template personas pretending to be research output (R2/R6)."""
    from bebshax.llm.failures import AllCandidatesFailed

    class _DeadLLM:
        async def complete(self, request):
            class _Prov:
                attempts: list = []

            raise AllCandidatesFailed(_Prov())

    with pytest.raises(AllCandidatesFailed):
        await generate_personas_for_study(
            study=_study_mock(),
            segments=[MockSegment("seg_1", "Budget Students", 100.0)],
            target_count=1,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=_DeadLLM(),
        )


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
