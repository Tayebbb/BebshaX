import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from bebshax_persona_ml.data import TrainingRecord
from bebshax_persona_ml.model import BusinessContext, PersonaModel, Selection

from bebshax.api.errors import APIError
from bebshax.persona.schema import CLAIM_GROUPS, ProvenanceClass
from bebshax.personas.ml_adapter import MLPersonaAdapter


async def test_missing_artifact_is_explicit_unavailable_without_local_path(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "private-artifacts" / "missing-model"
    adapter = MLPersonaAdapter(artifact_dir)

    with pytest.raises(APIError) as raised:
        await adapter.generate(BusinessContext(description="Food delivery for students"), num_personas=1)

    assert raised.value.status_code == 503
    assert raised.value.error_code == "ml_persona_unavailable"
    assert str(artifact_dir) not in raised.value.detail
    assert "private-artifacts" not in raised.value.detail


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_inference_concurrency_is_rejected(tmp_path: Path, limit) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        MLPersonaAdapter(tmp_path, max_concurrency=limit)


def test_missing_source_attributes_are_preserved_and_explicitly_warned(ml_training_records) -> None:
    from bebshax.personas.ml_adapter import to_persona_draft

    record = ml_training_records[0].model_copy(update={"education": "", "location": "", "behaviors": []})
    selection = Selection(record=record, score=0.5, topic=0, model_version="fixture")
    draft = to_persona_draft(selection)
    assert draft.behaviors == []
    assert draft.demographics["education"] == draft.demographics["location"] == "Not available in training data"
    assert draft.detailed_attributes["source_documents"] == record.documents
    for field in ("education", "location", "behaviors"):
        assert any(field in warning.casefold() for warning in draft.validation_warnings)
    assert draft.status == "needs_review"


async def test_corrupt_artifact_is_explicit_unavailable(ml_artifact: Path) -> None:
    (ml_artifact / "metadata.json").write_text("{}", encoding="utf-8")

    with pytest.raises(APIError) as raised:
        await MLPersonaAdapter(ml_artifact).generate(BusinessContext(description="Food delivery"), 1)

    assert raised.value.status_code == 503
    assert raised.value.error_code == "ml_persona_unavailable"
    assert "metadata.json" not in raised.value.detail


@pytest.mark.parametrize(
    ("context", "count"),
    [
        (BusinessContext(description="qzxwvyplm"), 1),
        (BusinessContext(description="Food delivery", min_age=90), 1),
        (BusinessContext(description="Food delivery"), 13),
        (BusinessContext(description="Food delivery"), 0),
    ],
)
async def test_unsupported_context_is_explicit_422(
    ml_artifact: Path, context: BusinessContext, count: int,
) -> None:
    with pytest.raises(APIError) as raised:
        await MLPersonaAdapter(ml_artifact).generate(context, count)

    assert raised.value.status_code == 422
    assert raised.value.error_code == "ml_persona_unsupported_context"
    assert str(ml_artifact) not in raised.value.detail


async def test_real_artifact_preserves_identity_and_excludes_source_ids(ml_artifact: Path) -> None:
    adapter = MLPersonaAdapter(ml_artifact)
    context = BusinessContext(description="Food delivery for students", role="Pilot", location="Dhaka")
    first = await adapter.generate(context, 3, seed=42)
    second = await adapter.generate(
        context, 3, seed=42,
        exclude_ids={selection.record.record_id for selection in first},
        exclude_names={selection.record.name for selection in first if selection.record.name},
    )

    assert len({selection.record.record_id for selection in [*first, *second]}) == 6
    assert all(selection.record.location == "Austin, Texas, USA" for selection in first)
    assert all(selection.record.occupation != "Pilot" for selection in first)
    assert all(any("role" in warning.lower() for warning in selection.warnings) for selection in first)


async def test_concurrent_generation_loads_once_off_event_loop(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_load = PersonaModel.load
    load_threads: list[int] = []

    def tracked_load(path: Path) -> PersonaModel:
        load_threads.append(threading.get_ident())
        return original_load(path)

    monkeypatch.setattr(PersonaModel, "load", tracked_load)
    adapter = MLPersonaAdapter(ml_artifact)
    batches = await asyncio.gather(*(
        adapter.generate(BusinessContext(description="Food delivery"), 1, seed=index)
        for index in range(6)
    ))

    assert all(len(batch) == 1 for batch in batches)
    assert len(load_threads) == 1
    assert load_threads[0] != threading.get_ident()


async def test_cancelled_requests_do_not_enqueue_waiters_or_release_running_inference(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    queued = asyncio.Event()
    release = threading.Event()
    worker_seeds: list[int | None] = []
    submitted: list[int | None] = []
    original_generate = PersonaModel.generate
    original_to_thread = asyncio.to_thread

    def controlled_generate(model, context, count, seed, exclude_ids, exclude_names):
        worker_seeds.append(seed)
        if seed == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(5), "Inference worker was not released"
        return original_generate(model, context, count, seed, exclude_ids, exclude_names)

    async def capture_submission(function, context, count, seed, exclude_ids, exclude_names):
        submitted.append(seed)
        return await original_to_thread(function, context, count, seed, exclude_ids, exclude_names)

    monkeypatch.setattr(PersonaModel, "generate", controlled_generate)
    monkeypatch.setattr(asyncio, "to_thread", capture_submission)
    adapter = MLPersonaAdapter(ml_artifact)
    context = BusinessContext(description="Food delivery and study planning")
    first = asyncio.create_task(adapter.generate(context, 1, seed=1))
    tasks = [first]
    try:
        await asyncio.wait_for(started.wait(), 5)
        cancelled_waiter = asyncio.create_task(adapter.generate(context, 1, seed=2))
        next_request = asyncio.create_task(adapter.generate(context, 1, seed=3))
        tasks.extend([cancelled_waiter, next_request])
        loop.call_soon(queued.set)
        await queued.wait()
        assert submitted == [1]
        cancelled_waiter.cancel()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_waiter
        with pytest.raises(asyncio.CancelledError):
            await first
        assert submitted == [1]
        release.set()
        selections = await asyncio.wait_for(next_request, 5)
        assert len(selections) == 1
        assert submitted == worker_seeds == [1, 3]
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("record_index", [0, 11])
def test_conversions_preserve_record_and_mark_every_claim_synthetic(
    ml_training_records: list[TrainingRecord], record_index: int,
) -> None:
    from bebshax.personas.ml_adapter import (
        to_generated_persona,
        to_persona_draft,
        to_persona_profile,
        to_workflow_persona,
    )

    record = ml_training_records[record_index]
    selection = Selection(record=record, score=0.75, topic=1, model_version="fixture-model")
    generated = to_generated_persona(selection)
    profile = to_persona_profile(selection, "business-fixture")
    draft = to_persona_draft(selection)
    workflow = to_workflow_persona(selection, role_id="pilot", role_title="Pilot")

    assert generated.name == (record.name or f"Synthetic profile {record.record_id}")
    assert generated.age == record.age
    assert generated.occupation == record.occupation
    assert generated.location == record.location
    assert generated.description == record.description
    assert generated.education == (record.education or "Not available in training data")
    assert generated.income_range == "Not available in training data"
    assert generated.personality is None
    assert generated.purchase_behavior == []
    for group in CLAIM_GROUPS:
        assert all(claim.provenance == "SYNTHETIC" and claim.evidence_ids == [] for claim in getattr(generated, group))
    assert profile.goals == record.goals
    assert profile.pain_points == record.pain_points
    assert profile.evidence == []
    assert all(attribute.provenance_class == ProvenanceClass.SYNTHETIC and not attribute.evidence_ids for attribute in profile.attributes)
    assert profile.generation_model == draft.generation_model == "bebshax-persona-ml/fixture-model"
    expected_provenance = {
        "source": record.source, "revision": record.revision, "record_id": record.record_id,
        "model_version": "fixture-model", "selection_score": 0.75, "topic": 1,
    }
    assert profile.detailed_attributes["ml_provenance"] == expected_provenance
    assert profile.detailed_attributes["source_documents"] == record.documents
    assert draft.detailed_attributes == profile.detailed_attributes
    assert draft.demographics["location"] == record.location
    assert draft.goals == record.goals
    assert draft.behaviors == record.behaviors
    assert draft.personality is None
    assert draft.commercial_profile == {}
    assert draft.evidence_citations == []
    assert draft.dataset_refs == [expected_provenance]
    assert draft.confidence == draft.grounding_score == 0.0
    assert draft.status == "needs_review"
    assert draft.detailed_attributes["validation_warnings"] == draft.validation_warnings
    assert profile.detailed_attributes["validation_warnings"] == profile.warnings
    for missing in ("income", "budget", "needs", "personality"):
        assert any(missing in warning.casefold() for warning in draft.validation_warnings)
    if not record.education:
        assert any("education" in warning.casefold() for warning in draft.validation_warnings)
    assert workflow["role_id"] == "pilot"
    assert workflow["role_title"] == "Pilot"
    assert workflow["demographics"] == draft.demographics
    assert workflow["occupation"] == record.occupation
    assert workflow["description"] == record.description
    assert workflow["dataset_refs"] == [expected_provenance]
    assert workflow["grounding_basis"] == "synthetic_training_proxy"
    assert all(attribute["provenance_class"] == "SYNTHETIC" and attribute["evidence_ids"] == [] for attribute in workflow["attributes"])
    assert any("USA" in warning and "proxy" in warning for warning in draft.validation_warnings)
    if record.name is None:
        assert any("name" in warning and "identifier" in warning for warning in profile.warnings)


def test_artifact_path_defaults_to_processed_root_and_accepts_admin_override(tmp_path: Path) -> None:
    from bebshax.config import Settings

    defaults = Settings.model_construct(data_dir=str(tmp_path))
    configured = Settings.model_construct(processed_dir=str(tmp_path / "processed-override"))
    override = Settings.model_construct(ml_persona_artifact_dir=str(tmp_path / "admin-model"))

    assert defaults.ml_persona_artifact_path == tmp_path / "processed" / "ml_persona" / "model"
    assert configured.ml_persona_artifact_path == tmp_path / "processed-override" / "ml_persona" / "model"
    assert override.ml_persona_artifact_path == tmp_path / "admin-model"


@pytest.mark.parametrize("fields", [
    {"description": "x" * 20001}, {"target_audience": "x" * 4001},
    {"price_range": "x" * 513}, {"role": "x" * 513},
    {"research": ["x" * 10001]}, {"features": ["x"] * 101},
    {"min_age": 17}, {"min_age": 40, "max_age": 20},
])
def test_context_limits_fail_explicitly_without_truncation(fields: dict) -> None:
    from bebshax.personas.ml_adapter import build_business_context

    with pytest.raises(APIError) as raised:
        build_business_context(**{"description": "Food delivery", **fields})
    assert raised.value.status_code == 422
    assert raised.value.error_code == "ml_persona_unsupported_context"


async def test_segment_generation_keeps_full_context_quotas_and_distinct_sources(
    ml_artifact: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bebshax.personas.generator import generate_personas_for_study

    study = SimpleNamespace(
        title="Meal planner", prompt="Food delivery for study and work",
        goal="pricing_validation", target_audience="Students in Dhaka",
        pricing_hypothesis="BDT 200 per month",
        collected_context={"customer_problem": "Unpredictable delivery fees", "sentinel": "context_tail"},
        findings={"research": "Students miss meal deadlines", "sentinel": "research_tail"},
    )
    segments = [
        SimpleNamespace(id="young", name="Young planners", description="Student schedules",
                        population_percentage=60.0, characteristics={"demographics": {"age_range": [18, 30]}}),
        SimpleNamespace(id="older", name="Working planners", description="Work schedules",
                        population_percentage=40.0, characteristics={"demographics": {"age_range": [31, 65]}}),
    ]
    claims = [SimpleNamespace(id=f"claim-{index}", claim_text=f"Meal planning research item {index}", category="problem")
              for index in range(7)]
    adapter = MLPersonaAdapter(ml_artifact)
    contexts: list[BusinessContext] = []
    original_generate = adapter.generate

    async def capture(context: BusinessContext, *args, **kwargs) -> list[Selection]:
        contexts.append(context)
        return await original_generate(context, *args, **kwargs)

    monkeypatch.setattr(adapter, "generate", capture)
    drafts = await generate_personas_for_study(
        study, segments, target_count=5, evidence_claims=claims, ml_generator=adapter,
    )

    assert [draft.segment_id for draft in drafts] == ["young", "young", "young", "older", "older"]
    assert len({draft.detailed_attributes["ml_provenance"]["record_id"] for draft in drafts}) == 5
    assert all(18 <= draft.demographics["age"] <= 30 for draft in drafts[:3])
    assert all(31 <= draft.demographics["age"] <= 65 for draft in drafts[3:])
    assert contexts[0].target_audience == study.target_audience
    assert contexts[0].price_range == study.pricing_hypothesis
    serialized = json.dumps(contexts[0].model_dump())
    for text in (study.prompt, study.goal, "context_tail", "research_tail", claims[-1].claim_text):
        assert text in serialized
    assert all(draft.evidence_citations == [] for draft in drafts)