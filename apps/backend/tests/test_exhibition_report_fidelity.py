"""Report context fidelity and explicit empty-claim output regressions."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.behavioral.orm import BehavioralTestResults, BehavioralTestRuns, BehavioralTests
from bebshax.db.models import (
    DatasetSources, EvidenceChunks, EvidenceClaims, EvidenceSources, MarketSegments, Personas, Studies,
)
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.failures import ContextWindowExceeded
from bebshax.llm.pools import POOLS
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import TaskType
from bebshax.research.claim_extractor import (
    CLAIMS_EXTRACTION_UNPARSEABLE,
    extract_claims_with_llm,
)
from bebshax.research.report_service import REPORT_SYSTEM_PROMPT, StudyReportService
from bebshax.utils.explicit_failures import UnusableModelOutput

_STUDY_ID = "study_report_fidelity"


def _make_router(reply: str, *, context_window: int = 100_000) -> tuple[PoolRouter, FakeAdapter]:
    adapter = FakeAdapter(
        routes=[
            FakeRoute(
                candidate=RouteCandidate(provider="pollinations", model="deepseek-r1", context_window=context_window),
                reply=reply,
            )
        ]
    )
    router = PoolRouter(
        {name: adapter for pool in POOLS.values() for name in pool.adapters}
    )
    return router, adapter


async def _capture_report_context(
    *,
    evidence_sources: list[EvidenceSources] | None = None,
    evidence_chunks: list[EvidenceChunks] | None = None,
    evidence_claims: list[EvidenceClaims] | None = None,
    datasets: list[DatasetSources] | None = None,
    segments: list[MarketSegments] | None = None,
    personas: list[Personas] | None = None,
    conversations: list[Conversations] | None = None,
    conversation_turns: list[ConversationTurns] | None = None,
    interview_insights: list[InterviewInsights] | None = None,
    behavioral_tests: list[BehavioralTests] | None = None,
    behavioral_runs: list[BehavioralTestRuns] | None = None,
    behavioral_results: list[BehavioralTestResults] | None = None,
    context_window: int = 100_000,
) -> dict[str, Any]:
    router, adapter = _make_router(
        json.dumps({"executive_summary": "Synthetic study records describe scheduling concerns."}),
        context_window=context_window,
    )
    study = Studies(
        id=_STUDY_ID,
        title="Synthetic scheduling study",
        prompt="A scheduling service for shift workers",
        goal="demand_validation",
        target_audience="Synthetic shift-worker profiles",
        pricing_hypothesis="Pricing has not been established.",
    )
    async with AsyncSession() as session:
        await StudyReportService(session, router)._synthesize_report_content(
            study=study,
            evidence_sources=evidence_sources or [],
            evidence_chunks=evidence_chunks or [],
            evidence_claims=evidence_claims or [],
            datasets=datasets or [],
            segments=segments or [],
            personas=personas or [],
            conversations=conversations or [],
            conversation_turns=conversation_turns or [],
            interview_insights=interview_insights or [],
            behavioral_tests=behavioral_tests or [],
            behavioral_runs=behavioral_runs or [],
            behavioral_results=behavioral_results or [],
            version=1,
        )

    assert len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.task == TaskType.REPORT_GENERATION
    assert request.json_mode is True
    user_messages = [message.content for message in request.messages if message.role == "user"]
    assert len(user_messages) == 1
    block = re.search(
        r"<UNTRUSTED_STUDY_CONTEXT\b[^>]*>\s*(.*?)\s*</UNTRUSTED_STUDY_CONTEXT>",
        user_messages[0],
        flags=re.DOTALL,
    )
    assert block is not None, "The report request must contain a delimited study context."
    context = json.loads(block.group(1))
    assert isinstance(context, dict)
    return context


def _claim(index: int) -> EvidenceClaims:
    return EvidenceClaims(
        id=f"claim_fidelity_{index}",
        study_id=_STUDY_ID,
        claim_text=f"Synthetic scheduling claim {index} has conflicting evidence.",
        status="contested",
        category="behavior",
        confidence=0.5,
        supporting_source_ids=[f"source_support_{index}"],
        supporting_chunk_ids=[f"chunk_support_{index}"],
        contradicting_source_ids=[f"source_conflict_{index}"],
        rationale=f"Source support {index} favors reminders; source conflict {index} disagrees.",
    )


def _persona(index: int) -> Personas:
    return Personas(
        id=f"persona_fidelity_{index}",
        study_id=_STUDY_ID,
        segment_id=f"segment_fidelity_{index}",
        generation_run_id=f"generation_fidelity_{index}",
        name=f"Synthetic participant {index}",
        status="needs_review",
        version=3,
        generation_model="fixture/source-selection",
        data_source="live",
        archetype=f"Shift-worker profile {index}",
        tagline=f"Balances rotating schedules and commute {index}.",
        country_code="US",
        demographics={"age": 25 + index, "occupation": "Shift worker", "location": "Austin"},
        personality={"openness": 0.4, "conscientiousness": 0.7},
        bio=f"Synthetic biography {index}; no observed customer behavior is claimed.",
        quote=f"I need to plan around shift changes {index}.",
        goals=[f"Goal {index}.{position}" for position in range(1, 4)],
        pain_points=[f"Pain point {index}.{position}" for position in range(1, 4)],
        needs=[f"Need {index}.{position}" for position in range(1, 4)],
        behaviors=[f"Behavior {index}.{position}" for position in range(1, 4)],
        preferences=[f"Preference {index}.{position}" for position in range(1, 4)],
        motivations=[f"Motivation {index}.{position}" for position in range(1, 4)],
        objections=[f"Objection {index}.{position}" for position in range(1, 4)],
        detailed_attributes={
            "constraints": [f"Unavailable during night shift {index}."],
            "claim_provenance": {
                "availability": {
                    "value": f"Night shift {index}",
                    "provenance": "SYNTHETIC",
                    "evidence_ids": [],
                }
            },
        },
        commercial_profile={"budget": f"Budget hypothesis {index}", "currency": "USD"},
        technology_profile={"device": "shared phone", "connectivity": "intermittent"},
        evidence_citations=[{"source_id": f"source_support_{index}", "chunk_id": f"chunk_support_{index}"}],
        dataset_refs=[{"dataset_id": f"dataset_fidelity_{index}", "version": 2}],
        grounding_score=0.0,
        confidence=0.0,
        validation_warnings=[f"Availability hypothesis {index} requires validation."],
        is_synthetic=True,
    )


def _insight(index: int) -> InterviewInsights:
    return InterviewInsights(
        id=f"insight_fidelity_{index}",
        interview_id=f"interview_fidelity_{index}",
        study_id=_STUDY_ID,
        persona_id=f"persona_fidelity_{index}",
        type="objection",
        title=f"Scheduling objection {index}",
        description=f"Synthetic participant {index} cannot accept reminders during a shift.",
        supporting_turn_numbers=[2, 4, 6],
        confidence=0.5,
        is_synthetic=True,
    )


def _evidence_inputs() -> tuple[list[EvidenceSources], list[EvidenceChunks]]:
    source = EvidenceSources(
        id="source_without_findings",
        study_id=_STUDY_ID,
        source_type="upload",
        title="Synthetic publication notice",
        content="This synthetic fixture records a publication date, with no product findings.",
        content_hash="a" * 64,
    )
    chunk = EvidenceChunks(
        id="chunk_without_findings",
        source_id=source.id,
        study_id=_STUDY_ID,
        chunk_index=0,
        content=source.content,
        embedding=[],
        embedding_space="fixture",
    )
    return [source], [chunk]


async def test_report_context_keeps_all_nine_claims_including_the_tail() -> None:
    claims = [_claim(index) for index in range(9)]

    context = await _capture_report_context(evidence_claims=claims)

    assert context["evidence_claims_count"] == 9
    captured_claims = context["evidence_claims_sample"]
    assert len(captured_claims) == 9
    assert [claim["claim"] for claim in captured_claims] == [claim.claim_text for claim in claims]
    assert captured_claims[-1]["claim"] == claims[-1].claim_text


async def test_report_context_keeps_all_seven_personas_including_the_tail() -> None:
    personas = [_persona(index) for index in range(7)]

    context = await _capture_report_context(personas=personas)

    assert context["personas_count"] == 7
    captured_personas = context["personas_sample"]
    assert len(captured_personas) == 7
    assert [persona["name"] for persona in captured_personas] == [persona.name for persona in personas]
    assert captured_personas[-1]["name"] == personas[-1].name


async def test_report_context_keeps_all_nine_insights_including_the_tail() -> None:
    insights = [_insight(index) for index in range(9)]

    context = await _capture_report_context(interview_insights=insights)

    captured_insights = context["interview_insights_sample"]
    assert len(captured_insights) == 9
    assert [insight["title"] for insight in captured_insights] == [insight.title for insight in insights]
    assert captured_insights[-1]["description"] == insights[-1].description


async def test_report_claim_retains_status_citations_conflicts_and_rationale() -> None:
    claim = _claim(0)

    context = await _capture_report_context(evidence_claims=[claim])

    captured = context["evidence_claims_sample"][0]
    expected = {
        "id": claim.id,
        "claim": claim.claim_text,
        "status": claim.status,
        "category": claim.category,
        "confidence": claim.confidence,
        "supporting_source_ids": claim.supporting_source_ids,
        "supporting_chunk_ids": claim.supporting_chunk_ids,
        "contradicting_source_ids": claim.contradicting_source_ids,
        "rationale": claim.rationale,
    }
    assert expected.keys() <= captured.keys()
    assert {field: captured[field] for field in expected} == expected


async def test_report_persona_retains_full_identity_attributes_and_provenance() -> None:
    persona = _persona(0)

    context = await _capture_report_context(personas=[persona])

    captured = context["personas_sample"][0]
    assert captured["goals"] == persona.goals
    assert captured["pain_points"] == persona.pain_points
    fields = (
        "id", "segment_id", "generation_run_id", "name", "status", "version",
        "generation_model", "data_source", "archetype", "tagline", "country_code",
        "demographics", "personality", "bio", "quote", "needs", "behaviors",
        "preferences", "motivations", "objections", "detailed_attributes",
        "commercial_profile", "technology_profile", "evidence_citations", "dataset_refs",
        "grounding_score", "confidence", "validation_warnings", "is_synthetic",
    )
    assert set(fields) <= captured.keys()
    for field in fields:
        assert captured[field] == getattr(persona, field), field


async def test_report_insight_retains_attribution_citations_and_synthetic_status() -> None:
    insight = _insight(0)

    context = await _capture_report_context(interview_insights=[insight])

    captured = context["interview_insights_sample"][0]
    expected = {
        "id": insight.id,
        "interview_id": insight.interview_id,
        "persona_id": insight.persona_id,
        "title": insight.title,
        "type": insight.type,
        "description": insight.description,
        "turns": insight.supporting_turn_numbers,
        "confidence": insight.confidence,
        "is_synthetic": insight.is_synthetic,
    }
    assert expected.keys() <= captured.keys()
    assert {field: captured[field] for field in expected} == expected


async def test_explicit_empty_claims_with_nonempty_evidence_returns_empty_after_one_call() -> None:
    sources, chunks = _evidence_inputs()
    router, adapter = _make_router(json.dumps({"claims": []}))

    claims = await extract_claims_with_llm(
        "A scheduling service for shift workers", sources, chunks, router
    )

    assert claims == []
    assert len(adapter.calls) == len(adapter.requests) == 1
    request = adapter.requests[0]
    assert request.task == TaskType.EVIDENCE_EXTRACTION
    assert chunks[0].id in request.messages[-1].content
    assert chunks[0].content in request.messages[-1].content


async def test_missing_claims_key_retries_then_raises_unusable_model_output() -> None:
    sources, chunks = _evidence_inputs()
    router, adapter = _make_router("{}")

    with pytest.raises(UnusableModelOutput) as failure:
        await extract_claims_with_llm(
            "A scheduling service for shift workers", sources, chunks, router
        )

    assert failure.value.error_code == CLAIMS_EXTRACTION_UNPARSEABLE
    assert failure.value.attempts == 2
    assert failure.value.served_by == "pollinations/deepseek-r1"
    assert len(adapter.calls) == len(adapter.requests) == 2
    first_request, retry_request = adapter.requests
    assert first_request.task == retry_request.task == TaskType.EVIDENCE_EXTRACTION
    assert first_request.request_id != retry_request.request_id
    assert first_request.messages == retry_request.messages


async def test_report_includes_full_source_and_chunk_text_with_citation_ids() -> None:
    sources, chunks = _evidence_inputs()
    sources[0].content = "Synthetic publication details. " * 300 + "Distinct final source statement."
    sources[0].metadata_payload = {"is_sample": True, "coverage": "Synthetic fixture only"}
    chunks[0].content = sources[0].content
    chunks[0].metadata_payload = {"source_title": sources[0].title}

    context = await _capture_report_context(evidence_sources=sources, evidence_chunks=chunks)

    assert context["evidence_sources"][0]["id"] == sources[0].id
    assert context["evidence_sources"][0]["content"] == sources[0].content
    assert context["evidence_sources"][0]["metadata_payload"] == sources[0].metadata_payload
    assert context["evidence_chunks"][0]["id"] == chunks[0].id
    assert context["evidence_chunks"][0]["source_id"] == sources[0].id
    assert context["evidence_chunks"][0]["content"] == chunks[0].content


async def test_report_keeps_all_dataset_profiles_and_segment_evidence() -> None:
    datasets = [DatasetSources(
        id=f"dataset_full_{index}", name=f"Synthetic dataset {index}", row_count=40,
        description=f"Synthetic fixture coverage {index}",
        schema_metadata={"is_sample": True, "limitations": ["Not population-representative"]},
        statistics={"budget": {"missing": 10, "currency": "USD"}},
        segments=[{"name": "Night shift", "uncertainty": "No observed data"}],
        content_hash=f"synthetic-dataset-hash-{index}", status="ready",
    ) for index in range(4)]
    segments = [MarketSegments(
        id=f"segment_full_{index}", study_id=_STUDY_ID, segmentation_run_id="seg_run_full",
        name=f"Synthetic segment {index}", description=f"Unvalidated segment hypothesis {index}",
        status="inference_assisted", characteristics={"availability": ["nights", "weekends"]},
        variable_distributions={"budget": {"unknown": 40}},
        evidence_citations=[{"source_id": f"source_{index}", "provenance": "SYNTHETIC"}],
    ) for index in range(6)]

    context = await _capture_report_context(datasets=datasets, segments=segments)

    assert [record["id"] for record in context["datasets_sample"]] == [dataset.id for dataset in datasets]
    for actual, expected in zip(context["datasets_sample"], datasets, strict=True):
        for field in ("schema_metadata", "statistics", "segments", "content_hash", "status", "description"):
            assert actual[field] == getattr(expected, field)
    assert [record["id"] for record in context["market_segments"]] == [segment.id for segment in segments]
    for actual, expected in zip(context["market_segments"], segments, strict=True):
        for field in ("status", "characteristics", "variable_distributions", "evidence_citations", "segmentation_run_id"):
            assert actual[field] == getattr(expected, field)


async def test_report_retains_transcript_text_memory_attribution_and_completion_status() -> None:
    conversations = [Conversations(
        id=f"conversation_full_{index}", study_id=_STUDY_ID, persona_id=f"persona_full_{index}",
        persona_version=3, objective="Explore scheduling constraints", status=status,
        configuration={"is_synthetic": True},
    ) for index, status in enumerate(("completed", "active"))]
    turns = [ConversationTurns(
        id=f"turn_full_{index}", conversation_id=conversations[0].id, turn_number=index + 1,
        role="persona", content=f"Synthetic scheduling response {index}. " * 60,
        served_by="fixture/conversation", retrieved_memories=[{"text": f"Complete remembered constraint {index}"}],
        metadata_json={"llm_request_id": f"request_full_{index}", "is_synthetic": True},
    ) for index in range(9)]

    context = await _capture_report_context(conversations=conversations, conversation_turns=turns)

    assert context["completed_interviews"] == 1
    assert [record["id"] for record in context["conversations"]] == [conversation.id for conversation in conversations]
    assert context["conversations"][1]["status"] == "active"
    assert context["conversations"][0]["persona_version"] == 3
    assert len(context["conversation_turns"]) == len(turns)
    for actual, expected in zip(context["conversation_turns"], turns, strict=True):
        for field in ("id", "conversation_id", "turn_number", "role", "content", "served_by", "retrieved_memories", "metadata_json"):
            assert actual[field] == getattr(expected, field)


async def test_report_keeps_all_simulation_results_and_full_run_provenance() -> None:
    tests = [BehavioralTests(
        id=f"behavioral_full_{index}", study_id=_STUDY_ID, name=f"Synthetic scenario {index}",
        test_type="pricing_test", description="Unvalidated price hypothesis", configuration={"price": None},
    ) for index in range(5)]
    runs = [BehavioralTestRuns(
        id=f"behavioral_run_full_{index}", study_id=_STUDY_ID, behavioral_test_id=tests[0].id,
        status="completed_with_warnings", scenario_id=f"scenario_{index}",
        scenario_snapshot={"text": f"Complete tested scenario {index}"},
        target_persona_ids=[f"persona_full_{index}"], aggregate_metrics={"failed_count": 1},
        risks=[{"reason": "Synthetic signals only"}], opportunities=[{"hypothesis": "Test with real customers"}],
    ) for index in range(7)]
    results = [BehavioralTestResults(
        id=f"result_full_{index}", study_id=_STUDY_ID, test_run_id=runs[index].id,
        behavioral_test_id=tests[0].id, persona_id=f"persona_full_{index}", persona_name=f"Synthetic profile {index}",
        decision="unlikely_to_buy", decision_label="Unlikely to buy", confidence="low", confidence_score=0.2,
        probability=0.1, key_factors=[{"factor": "Unknown budget"}],
        motivators=[f"Motivator {position}" for position in range(4)],
        objections=[f"Objection {position}" for position in range(4)],
        reasoning_summary=f"Synthetic reasoning {index}; no validated demand.",
        simulation_context_sources={"persona": "SYNTHETIC"}, interview_signals_used=["Uncertain price tolerance"],
        provenance_id=f"request_simulation_{index}", status="completed",
    ) for index in range(7)]

    context = await _capture_report_context(behavioral_tests=tests, behavioral_runs=runs, behavioral_results=results)

    assert len(context["behavioral_simulations"]) == len(tests)
    assert len(context["behavioral_runs"]) == len(runs)
    assert context["behavioral_runs"][-1]["scenario_snapshot"] == runs[-1].scenario_snapshot
    assert context["behavioral_runs"][-1]["risks"] == runs[-1].risks
    assert len(context["behavioral_results_sample"]) == len(results)
    for actual, expected in zip(context["behavioral_results_sample"], results, strict=True):
        for field in ("id", "test_run_id", "persona_id", "confidence", "confidence_score", "motivators", "objections",
                      "reasoning_summary", "simulation_context_sources", "interview_signals_used", "provenance_id", "status"):
            assert actual[field] == getattr(expected, field)


def test_report_prompt_discloses_uncertainty_synthetic_limits_and_no_entailment_validation() -> None:
    assert "contested" in REPORT_SYSTEM_PROMPT and "uncertainty" in REPORT_SYSTEM_PROMPT
    assert "synthetic" in REPORT_SYSTEM_PROMPT and "validated demand" in REPORT_SYSTEM_PROMPT
    assert "No automated entailment validation" in REPORT_SYSTEM_PROMPT
    assert "scores null" in REPORT_SYSTEM_PROMPT


async def test_oversized_full_persona_context_fails_explicitly_instead_of_clipping() -> None:
    persona = _persona(0)
    persona.bio = "Full synthetic biography and constraints must remain intact. " * 2_000

    with pytest.raises(ContextWindowExceeded):
        await _capture_report_context(personas=[persona], context_window=10_000)


async def test_claim_extraction_includes_every_chunk_and_preserves_tail_text() -> None:
    sources, _ = _evidence_inputs()
    chunks = [EvidenceChunks(
        id=f"full_chunk_{index}", source_id=sources[0].id, study_id=_STUDY_ID, chunk_index=index,
        content=f"Synthetic scheduling observation {index}. " * 40 + f"Final qualifier {index}.",
        embedding=[], embedding_space="fixture",
    ) for index in range(13)]
    router, adapter = _make_router('{"claims": []}')

    assert await extract_claims_with_llm("Synthetic scheduling", sources, chunks, router) == []

    assert len(adapter.requests) == 1
    prompt = adapter.requests[0].messages[-1].content
    for chunk in chunks:
        assert chunk.id in prompt
        assert chunk.content in prompt