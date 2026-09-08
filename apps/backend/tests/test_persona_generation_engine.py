"""Unit and integration tests for synthetic persona generation engine and validator."""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.db.models import Base, MarketSegments, Studies
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
async def test_generate_personas_without_llm_fails_explicitly():
    """No LLM wired → an explicit LLMUnavailable, never template personas."""
    from bebshax.utils.explicit_failures import LLMUnavailable

    segments = [
        MockSegment("seg_1", "Budget Students", 65.0),
        MockSegment("seg_2", "Ambitious Preppers", 35.0),
    ]
    mock_study = MagicMock()
    mock_study.title = "Exam Prep Platform"
    mock_study.prompt = "Affordable study planning"
    mock_study.target_audience = "College students"
    mock_study.pricing_hypothesis = "৳300/month"

    with pytest.raises(LLMUnavailable) as exc_info:
        await generate_personas_for_study(
            study=mock_study,
            segments=segments,
            target_count=4,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=None,
        )
    assert exc_info.value.error_code == "llm_unavailable"
    assert exc_info.value.status_code == 503


def _payload(request) -> dict:
    """The study/segment JSON the generator sends inside its untrusted block."""
    import json as _json

    content = request.messages[-1].content
    return _json.loads(content[content.index("{") : content.rindex("}") + 1])


class _SegmentAwareLLM:
    """Writes `count_to_generate` distinct personas for whatever segment it is
    shown — stands in for the model in service-level tests."""

    def __init__(self, provider: str = "fake", model: str = "m1") -> None:
        self._provider, self._model = provider, model
        self.calls = 0

    async def complete(self, request):
        import json as _json
        from types import SimpleNamespace

        self.calls += 1
        payload = _payload(request)
        seg = payload.get("segment", {}).get("name", "Segment")
        n = payload["count_to_generate"]
        personas = [
            {
                "name": f"{seg} persona {self.calls}-{i}",
                "age": 21 + i,
                "occupation": "Student",
                "location": "Dhaka",
                "monthly_budget": 400,
                "currency": "BDT",
                "goals": [{"value": "pass exams", "provenance": "SYNTHETIC", "evidence_ids": []}],
                "needs": ["cheap plans"],
                "pain_points": ["expensive coaching"],
            }
            for i in range(n)
        ]
        return SimpleNamespace(
            text=_json.dumps({"personas": personas}),
            provenance=SimpleNamespace(served_by_provider=self._provider, served_by_model=self._model),
        )


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
async def test_malformed_llm_output_is_retried_once_then_fails_explicitly():
    """An unusable reply is retried once per batch; a second unusable reply is
    an explicit UnusableModelOutput — never template personas."""
    from bebshax.utils.explicit_failures import UnusableModelOutput

    calls: list[int] = []

    class _CountingGarbageLLM(_FakeLLM):
        async def complete(self, request):
            calls.append(1)
            return await super().complete(request)

    with pytest.raises(UnusableModelOutput) as exc_info:
        await generate_personas_for_study(
            study=_study_mock(),
            segments=[MockSegment("seg_1", "Budget Students", 100.0)],
            target_count=2,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=_CountingGarbageLLM("this is not json at all", provider="fake", model="m9"),
        )
    assert len(calls) == 2  # exactly one retry
    err = exc_info.value
    assert err.error_code == "persona_generation_unparseable"
    assert err.status_code == 502
    assert err.extra["attempts"] == 2 and err.extra["served_by"] == "fake/m9"
    assert err.extra["segment"] == "Budget Students"


@pytest.mark.asyncio
async def test_absent_fields_stay_absent_no_regional_or_template_backfill():
    """A persona the model wrote WITHOUT location/personality/quote/platforms
    must be stored without them — never 'Dhaka, Bangladesh', Big-Five 50s,
    bKash platforms or a stock quote stamped with the LLM's name."""
    import json as _json

    reply = _json.dumps(
        {
            "personas": [
                {
                    "name": "Dr. Elena Vargas",
                    "age": 41,
                    "occupation": "Dental practice owner",
                    "goals": ["reduce no-shows"],
                    "pain_points": ["paper reminders"],
                }
            ]
        }
    )
    study = MagicMock()
    study.title = "CRM for dental clinics in Texas"
    study.prompt = "Appointment reminders and billing for small dental practices"
    study.target_audience = "Dentists running 1-3 chair practices in Texas"
    study.pricing_hypothesis = "$79 per month"

    [d] = await generate_personas_for_study(
        study=study,
        segments=[MockSegment("seg_1", "Practice owners", 100.0, 30, 60, 50, 200)],
        target_count=1,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_FakeLLM(reply, provider="llm7", model="codestral-latest"),
    )
    assert d.generation_model == "llm7/codestral-latest"
    assert "location" not in d.demographics
    assert d.personality is None
    assert d.quote is None and d.tagline is None and d.bio is None
    assert d.technology_profile == {} and d.commercial_profile == {}
    assert d.country_code is None and d.origin_country is None
    assert d.needs == []  # not filled from a template
    blob = _json.dumps(d.model_dump(), ensure_ascii=False).lower()
    for forbidden in ("dhaka", "bangladesh", "bkash", "khichuri", "cost-effective service", "night caregiver"):
        assert forbidden not in blob, forbidden


def test_currency_hint_is_derived_from_the_study_text_only():
    from bebshax.personas.generator import infer_currency_hint

    assert infer_currency_hint({"pricing_hypothesis": "৳300/month"}) == "BDT"
    assert infer_currency_hint({"pricing_hypothesis": "$79 per month"}) == "USD"
    assert infer_currency_hint({"prompt": "KSh 200 weekly solar lease"}) == "KES"
    # nothing in the text → None: the model infers from the audience, we assume nothing
    assert infer_currency_hint({"prompt": "a planner app", "target_audience": "students"}) is None


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
async def test_claims_written_by_the_model_are_all_classed():
    """Every classed group the model wrote carries a provenance entry; a group the
    model omitted is empty — not filled from anywhere."""
    import json as _json

    reply = _json.dumps(
        {
            "personas": [
                {
                    "name": "Tania Rahman",
                    "age": 22,
                    "occupation": "Student",
                    "goals": [{"value": "pass exams", "provenance": "SYNTHETIC", "evidence_ids": []}],
                    "pain_points": ["expensive coaching"],
                }
            ]
        }
    )
    [d] = await generate_personas_for_study(
        study=_study_mock(),
        segments=[MockSegment("seg_1", "Budget Students", 100.0)],
        target_count=1,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_FakeLLM(reply),
    )
    prov = d.detailed_attributes["claim_provenance"]
    assert prov["goals"] == [{"value": "pass exams", "provenance": "SYNTHETIC", "evidence_ids": []}]
    assert prov["pain_points"] == [{"value": "expensive coaching", "provenance": "SYNTHETIC", "evidence_ids": []}]
    assert prov["needs"] == [] and d.needs == []


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

            payload = _payload(request)
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

        service = PersonaGenerationService(session, llm_service=_SegmentAwareLLM())

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


# ---------------------------------------------------------------------------
# Fix-1 regression tests — concurrent segment generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_generation_preserves_segment_order():
    """Segments complete in reverse order (slowest first) but output must still
    be in the declared segment order (seg_a personas before seg_b personas)."""
    import asyncio as _asyncio
    import json as _json

    class _DelayedLLM:
        def __init__(self, delay: float, prefix: str) -> None:
            self._delay = delay
            self._prefix = prefix

        async def complete(self, request):
            from types import SimpleNamespace
            payload = _payload(request)
            n = payload["count_to_generate"]
            await _asyncio.sleep(self._delay)
            personas = [
                {
                    "name": f"{self._prefix}-{i}",
                    "age": 22,
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

    # seg_a is slower — would finish last without concurrency, but its personas
    # must still appear first in the output because it is declared first.
    segments = [
        MockSegment("seg_a", "Slow Segment", 50.0),
        MockSegment("seg_b", "Fast Segment", 50.0),
    ]
    mock_study = MagicMock()
    mock_study.title = "Order Test"
    mock_study.prompt = ""
    mock_study.target_audience = "Students"
    mock_study.pricing_hypothesis = ""

    # Use a shared LLM that tracks which segment completed first via delay
    completion_order: list[str] = []

    class _TrackingLLM:
        def __init__(self, delay: float, tag: str) -> None:
            self._delay = delay
            self._tag = tag

        async def complete(self, request):
            from types import SimpleNamespace
            payload = _payload(request)
            n = payload["count_to_generate"]
            await _asyncio.sleep(self._delay)
            completion_order.append(self._tag)
            personas = [
                {
                    "name": f"Persona-{self._tag}-{i}",
                    "age": 22,
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

    # Patch _process_segment to use different LLM instances per segment
    # Instead, use a shared LLM that dispatches by segment name via payload
    class _OrderTestLLM:
        async def complete(self, request):
            from types import SimpleNamespace
            payload = _payload(request)
            n = payload["count_to_generate"]
            seg_name = payload.get("segment", {}).get("name", "")
            delay = 0.05 if "Slow" in seg_name else 0.01
            await _asyncio.sleep(delay)
            completion_order.append(seg_name)
            personas = [
                {
                    "name": f"Persona-{seg_name}-{i}",
                    "age": 22,
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
        study=mock_study,
        segments=segments,
        target_count=2,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_OrderTestLLM(),
    )

    assert len(drafts) == 2
    # Fast segment completed first, but output must be in declared segment order
    assert "Slow Segment" in completion_order[1], "Fast Segment should finish first"
    # Output personas must be in segment declaration order
    assert "Slow Segment" in drafts[0].name
    assert "Fast Segment" in drafts[1].name


@pytest.mark.asyncio
async def test_one_failing_segment_fails_the_run_explicitly():
    """A non-LLM exception inside one segment must surface — the run must not
    quietly deliver template personas for that segment (R2)."""
    import json as _json

    class _PartiallyDeadLLM:
        """Fails for 'Bad Segment', succeeds for all others."""

        async def complete(self, request):
            from types import SimpleNamespace
            payload = _payload(request)
            seg_name = payload.get("segment", {}).get("name", "")
            n = payload["count_to_generate"]
            if seg_name == "Bad Segment":
                raise RuntimeError("simulated transient provider error")
            personas = [
                {
                    "name": f"OK-{seg_name}-{i}",
                    "age": 22,
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

    segments = [
        MockSegment("seg_a", "Good Segment A", 33.0),
        MockSegment("seg_b", "Bad Segment", 34.0),
        MockSegment("seg_c", "Good Segment C", 33.0),
    ]
    mock_study = MagicMock()
    mock_study.title = "Partial Failure Test"
    mock_study.prompt = ""
    mock_study.target_audience = "Mixed"
    mock_study.pricing_hypothesis = ""

    with pytest.raises(RuntimeError, match="simulated transient provider error"):
        await generate_personas_for_study(
            study=mock_study,
            segments=segments,
            target_count=3,
            distribution_strategy="equal",
            evidence_claims=[],
            llm_service=_PartiallyDeadLLM(),
        )


@pytest.mark.asyncio
async def test_non_numeric_age_is_stored_as_absent_not_templated():
    """A value that cannot be normalised (age 'twenty-two') is simply absent on
    the draft; the run still delivers exactly target_count model-written personas."""
    import json as _json

    class _PostCallPoisonLLM:
        async def complete(self, request):
            from types import SimpleNamespace
            payload = _payload(request)
            seg_name = payload.get("segment", {}).get("name", "")
            n = payload["count_to_generate"]
            age = "twenty-two" if seg_name == "Poison Segment" else 22
            personas = [
                {
                    "name": f"P-{seg_name}-{i}",
                    "age": age,
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

    segments = [
        MockSegment("seg_ok", "Clean Segment", 50.0),
        MockSegment("seg_bad", "Poison Segment", 50.0),
    ]
    mock_study = MagicMock()
    mock_study.title = "Post-call failure test"
    mock_study.prompt = ""
    mock_study.target_audience = "Mixed"
    mock_study.pricing_hypothesis = ""

    drafts = await generate_personas_for_study(
        study=mock_study,
        segments=segments,
        target_count=4,
        distribution_strategy="equal",
        evidence_claims=[],
        llm_service=_PostCallPoisonLLM(),
    )

    assert len(drafts) == 4
    assert all(d.generation_model == "fake/m1" for d in drafts)
    poisoned = [d for d in drafts if "Poison Segment" in d.name]
    assert len(poisoned) == 2 and all("age" not in d.demographics for d in poisoned)
    clean = [d for d in drafts if "Clean Segment" in d.name]
    assert all(d.demographics["age"] == 22 for d in clean)


@pytest.mark.asyncio
async def test_evidence_snapshot_records_the_true_claim_count():
    """claim_count is provenance about the study, not about the prompt budget:
    a study with more claims than _CLAIM_FETCH_LIMIT must record the real total."""
    from bebshax.db.models import EvidenceClaims
    from bebshax.personas.service import _CLAIM_FETCH_LIMIT

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    total_claims = _CLAIM_FETCH_LIMIT + 5
    async with session_maker() as session:
        session.add(Studies(id="std_claim_count", title="Claim Count Study", status="active"))
        session.add(
            MarketSegments(
                id="seg_claim_count",
                study_id="std_claim_count",
                segmentation_run_id="srun_cc",
                name="Segment",
                cluster_label="cluster_0",
                description="Segment used for claim-count provenance",
                population_count=100,
                population_percentage=100.0,
                characteristics={
                    "demographics": {"age_range": [19, 23]},
                    "economics": {"monthly_budget": {"min": 300, "max": 600, "median": 450}},
                },
            )
        )
        for i in range(total_claims):
            session.add(
                EvidenceClaims(
                    id=f"clm_{i}",
                    study_id="std_claim_count",
                    claim_text=f"Claim {i}",
                    category="general",
                    confidence=0.5,
                )
            )
        await session.commit()

        service = PersonaGenerationService(session, llm_service=_SegmentAwareLLM())
        run, _ = await service.create_generation_run(
            study_id="std_claim_count", target_count=2, distribution_strategy="equal"
        )

        assert run.evidence_snapshot["claim_count"] == total_claims
        assert run.evidence_snapshot["claims_used_count"] == _CLAIM_FETCH_LIMIT
