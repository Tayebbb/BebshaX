"""Database-backed report cohort selection and historical evidence regressions."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.behavioral.orm import BehavioralTestResults, BehavioralTestRuns, BehavioralTests
from bebshax.db.models import Base, Personas, Studies, StudyReports
from bebshax.interview.orm import Conversations, ConversationTurns
from bebshax.llm.adapters.base import RouteCandidate
from bebshax.llm.adapters.fake import FakeAdapter, FakeRoute
from bebshax.llm.pools import POOLS
from bebshax.llm.router import PoolRouter
from bebshax.llm.types import TaskType
from bebshax.research.report_service import StudyReportService

_STUDY_ID = "study_cohort"
_FOREIGN_STUDY_ID = "study_foreign_cohort"


@pytest.fixture
async def cohort_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'report_cohort.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=True)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("current_status", "include_history"),
    [("active", False), ("ready", False), ("needs_review", False), ("draft", False), ("active", True)],
)
async def test_report_persona_cohort_preserves_only_current_and_study_evidenced_profiles(
    cohort_sessions: async_sessionmaker[AsyncSession],
    current_status: str,
    include_history: bool,
) -> None:
    persona_rows = [
        Personas(id="current", study_id=_STUDY_ID, name="Cecelia", status=current_status,
                 demographics={"age": 25}, bio="Complete current profile."),
        Personas(id="unused", study_id=_STUDY_ID, name="Morgan", status="archived",
                 demographics={"age": 71}, bio="Unused archived source profile."),
        Personas(id="foreign_conversation_only", study_id=_STUDY_ID,
                 name="Foreign conversation reference", status="archived"),
        Personas(id="foreign_result_only", study_id=_STUDY_ID,
                 name="Foreign result reference", status="archived"),
        Personas(id="foreign_current", study_id=_FOREIGN_STUDY_ID, name="Foreign current", status="ready"),
        Personas(id="foreign_archived", study_id=_FOREIGN_STUDY_ID, name="Foreign archived", status="archived"),
    ]
    conversation_specs = [
        ("current_interview", _STUDY_ID, "current"),
        ("foreign_interview", _FOREIGN_STUDY_ID, "foreign_conversation_only"),
        ("foreign_archived_interview", _FOREIGN_STUDY_ID, "foreign_archived"),
    ]
    result_specs = [("foreign_result", _FOREIGN_STUDY_ID, "foreign_result_only")]
    expected_personas = {"current"}
    if include_history:
        for persona_id in ("historical_interview", "historical_behavior", "historical_both"):
            persona_rows.append(Personas(
                id=persona_id, study_id=_STUDY_ID, name=persona_id, status="archived",
                bio=f"Complete historical profile for {persona_id}.",
            ))
            expected_personas.add(persona_id)
        conversation_specs.extend([
            ("archived_interview", _STUDY_ID, "historical_interview"),
            ("both_interview", _STUDY_ID, "historical_both"),
        ])
        result_specs.extend([
            ("archived_result", _STUDY_ID, "historical_behavior"),
            ("both_result", _STUDY_ID, "historical_both"),
        ])
    expected_conversations = {
        conversation_id for conversation_id, study_id, _ in conversation_specs if study_id == _STUDY_ID
    }
    expected_results = {result_id for result_id, study_id, _ in result_specs if study_id == _STUDY_ID}
    source_statuses = {persona.id: persona.status for persona in persona_rows}

    async with cohort_sessions() as session:
        session.add_all([
            Studies(id=_STUDY_ID, title="Cohort study", persona_count=1),
            Studies(id=_FOREIGN_STUDY_ID, title="Foreign study"),
            StudyReports(id="past_report", study_id=_STUDY_ID, version=1,
                         title="Immutable past report", executive_summary="Original synthetic findings.",
                         metrics={"total_personas": 2}),
            *persona_rows,
        ])
        await session.flush()
        for conversation_id, study_id, persona_id in conversation_specs:
            session.add(Conversations(
                id=conversation_id, study_id=study_id, persona_id=persona_id,
                objective="Explore scheduling", status="completed", turn_count=6,
            ))
        await session.flush()
        for conversation_id, _, _ in conversation_specs:
            for turn_number in range(1, 7):
                session.add(ConversationTurns(
                    id=f"{conversation_id}_{turn_number}", conversation_id=conversation_id,
                    turn_number=turn_number, role="persona",
                    content=f"Full answer {turn_number} from {conversation_id}.",
                ))
        for result_id, study_id, persona_id in result_specs:
            session.add(BehavioralTests(id=f"test_{result_id}", study_id=study_id, name=result_id))
            await session.flush()
            session.add(BehavioralTestRuns(
                id=f"run_{result_id}", behavioral_test_id=f"test_{result_id}",
                study_id=study_id, status="completed", persona_count=1,
            ))
            await session.flush()
            session.add(BehavioralTestResults(
                id=result_id, test_run_id=f"run_{result_id}", behavioral_test_id=f"test_{result_id}",
                study_id=study_id, persona_id=persona_id, persona_name=persona_id,
                decision="neutral", decision_label="Uncertain",
                reasoning_summary=f"Full historical reasoning for {result_id}.",
                objections=[f"Unresolved objection for {result_id}."],
            ))
        await session.commit()

    adapter = FakeAdapter([FakeRoute(
        candidate=RouteCandidate(provider="pollinations", model="deepseek-r1", context_window=100_000),
        reply=json.dumps({"executive_summary": "Synthetic scheduling signals require real customer validation."}),
    )])
    router = PoolRouter({name: adapter for pool in POOLS.values() for name in pool.adapters})
    async with cohort_sessions() as session:
        report = await StudyReportService(session, router).generate_report(_STUDY_ID)
        assert len(adapter.requests) == 1
        request = adapter.requests[0]
        assert request.task == TaskType.REPORT_GENERATION
        user_message = next(message.content for message in request.messages if message.role == "user")
        block = re.search(
            r"<UNTRUSTED_STUDY_CONTEXT\b[^>]*>\s*(.*?)\s*</UNTRUSTED_STUDY_CONTEXT>",
            user_message, flags=re.DOTALL,
        )
        assert block is not None
        context = json.loads(block.group(1))
        assert {persona["id"] for persona in context["personas_sample"]} == expected_personas
        assert context["personas_count"] == len(context["personas_sample"]) == len(expected_personas)
        current = next(persona for persona in context["personas_sample"] if persona["id"] == "current")
        assert current["demographics"] == {"age": 25}
        assert current["bio"] == "Complete current profile."
        for persona in context["personas_sample"]:
            if persona["id"] != "current":
                assert persona["status"] == "archived"
                assert persona["bio"] == f"Complete historical profile for {persona['id']}."
        assert {conversation["id"] for conversation in context["conversations"]} == expected_conversations
        assert {turn["id"]: turn["content"] for turn in context["conversation_turns"]} == {
            f"{conversation_id}_{turn_number}": f"Full answer {turn_number} from {conversation_id}."
            for conversation_id in expected_conversations for turn_number in range(1, 7)
        }
        assert {result["id"] for result in context["behavioral_results_sample"]} == expected_results
        for result in context["behavioral_results_sample"]:
            assert result["reasoning_summary"] == f"Full historical reasoning for {result['id']}."
            assert result["objections"] == [f"Unresolved objection for {result['id']}."]
        assert report.metrics["total_personas"] == len(expected_personas)
        assert report.metrics["total_interviews"] == len(expected_conversations)
        assert report.version == 2

    async with cohort_sessions() as session:
        stored_personas = list((await session.execute(select(Personas))).scalars())
        assert {persona.id: persona.status for persona in stored_personas} == source_statuses
        past_report = await session.get(StudyReports, "past_report")
        assert past_report is not None
        assert past_report.version == 1
        assert past_report.title == "Immutable past report"
        assert past_report.metrics == {"total_personas": 2}
        study = await session.get(Studies, _STUDY_ID)
        assert study is not None and study.findings is not None
        assert study.persona_count == 1
        assert study.findings["version"] == 2
        assert study.findings["metrics"]["total_personas"] == len(expected_personas)