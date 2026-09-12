"""Behavioral Testing REST API: study-scoped simulation creation, batch execution, live progress, and results."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user, get_optional_current_user
from bebshax.api.deps import get_session, user_can_write_study, user_owns_study
from bebshax.api.errors import APIError
from bebshax.api.jobs import cancel_job_async, get_job_async, start_job_async
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.behavioral.engine import BehavioralSimulationEngine
from bebshax.behavioral.orm import (
    BehavioralInsights,
    BehavioralTestResults,
    BehavioralTestRuns,
    BehavioralTestScenarios,
    BehavioralTests,
)
from bebshax.db.models import Personas, Studies
from bebshax.jobs.store import input_snapshot
from bebshax.jobs.runtime import JobContext
from bebshax.llm.failures import LLMError
from bebshax.utils.explicit_failures import LLMUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(tags=["behavioral-testing"])

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_owner(column: Any, user: Optional[Users]) -> Any:
    return column.is_(None) if user is None else (column.is_(None) | (column == user.id))


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class CreateBehavioralTestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=5000)
    test_type: str = Field(
        default="pricing_test",
        pattern="^(purchase_decision|pricing_test|feature_test|concept_test|message_test|offer_test|switching_test|objection_test)$",
    )
    configuration: dict = Field(default_factory=dict)
    scenario_title: Optional[str] = Field(default=None, max_length=256)
    scenario_text: Optional[str] = Field(default=None, max_length=10000)


class UpdateBehavioralTestRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)
    description: Optional[str] = Field(default=None, max_length=5000)
    test_type: Optional[str] = None
    configuration: Optional[dict] = None
    status: Optional[str] = None
    scenario_title: Optional[str] = Field(default=None, max_length=256)
    scenario_text: Optional[str] = Field(default=None, max_length=10000)


class RunBehavioralTestRequest(BaseModel):
    scenario_id: Optional[str] = Field(default=None, max_length=64)
    scenario_title: Optional[str] = Field(default=None, max_length=256)
    scenario_text: Optional[str] = Field(default=None, max_length=10000)
    parameters: Optional[dict] = None
    target_population_type: str = Field(default="all", pattern="^(all|segment|selected_personas)$")
    target_segment_id: Optional[str] = Field(default=None, max_length=64)
    target_persona_ids: Optional[list[Annotated[str, Field(min_length=1, max_length=64)]]] = Field(default=None, max_length=50)

    @field_validator("parameters")
    @classmethod
    def bounded_parameters(cls, value: Optional[dict]) -> Optional[dict]:
        pending: list[tuple[Any, int]] = [(value, 0)]
        count = 0
        while pending:
            item, depth = pending.pop()
            count += 1
            if depth > 8 or count > 2048:
                raise ValueError("Scenario parameters exceed the nesting or item limit.")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        if len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")) > 65536:
            raise ValueError("Scenario parameters exceed 64 KiB.")
        return value


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_test(t: BehavioralTests, scenarios: Optional[Sequence[BehavioralTestScenarios]] = None, runs: Optional[Sequence[BehavioralTestRuns]] = None) -> dict[str, Any]:
    latest_run = runs[0] if runs else None
    return {
        "id": t.id,
        "study_id": t.study_id,
        "name": t.name,
        "description": t.description,
        "test_type": t.test_type,
        "configuration": t.configuration or {},
        "status": t.status,
        "scenarios": [
            {
                "id": s.id,
                "title": s.title,
                "scenario_text": s.scenario_text,
                "structured_parameters": s.structured_parameters or {},
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in (scenarios or [])
        ],
        "run_count": len(runs) if runs is not None else 0,
        "latest_run": {
            "id": latest_run.id,
            "status": latest_run.status,
            "persona_count": latest_run.persona_count,
            "completed_count": latest_run.completed_count,
            "average_likelihood": (latest_run.aggregate_metrics or {}).get("average_likelihood", 0.5),
            "created_at": latest_run.created_at.isoformat() if latest_run.created_at else None,
        } if latest_run else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _serialize_run(r: BehavioralTestRuns, results: Optional[Sequence[BehavioralTestResults]] = None, insights: Optional[Sequence[BehavioralInsights]] = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "behavioral_test_id": r.behavioral_test_id,
        "study_id": r.study_id,
        "scenario_id": r.scenario_id,
        "scenario_snapshot": r.scenario_snapshot or {},
        "target_population_type": r.target_population_type,
        "target_segment_id": r.target_segment_id,
        "target_persona_ids": r.target_persona_ids or [],
        "status": "running" if r.status == "retry_pending" else r.status,
        "persona_count": r.persona_count,
        "completed_count": r.completed_count,
        "failed_count": r.failed_count,
        "aggregate_metrics": r.aggregate_metrics or {},
        "segment_analysis": r.segment_analysis or [],
        "cross_persona_patterns": r.cross_persona_patterns or {},
        "risks": r.risks or [],
        "opportunities": r.opportunities or [],
        "summary": r.summary,
        "error_message": r.error_message,
        "results": [
            {
                "id": res.id,
                "persona_id": res.persona_id,
                "persona_name": res.persona_name,
                "persona_version": res.persona_version,
                "segment_id": res.segment_id,
                "segment_name": res.segment_name,
                "decision": res.decision,
                "decision_label": res.decision_label,
                "probability": res.probability,
                "confidence": res.confidence,
                "confidence_score": res.confidence_score,
                "key_factors": res.key_factors or [],
                "motivators": res.motivators or [],
                "objections": res.objections or [],
                "reasoning_summary": res.reasoning_summary,
                "simulation_context_sources": res.simulation_context_sources or {},
                "interview_signals_used": res.interview_signals_used or [],
                "status": res.status,
                "error_message": res.error_message,
                "created_at": res.created_at.isoformat() if res.created_at else None,
            }
            for res in (results or [])
        ],
        "insights": [
            {
                "id": ins.id,
                "type": ins.type,
                "title": ins.title,
                "description": ins.description,
                "supporting_persona_ids": ins.supporting_persona_ids or [],
                "confidence": ins.confidence,
                "is_synthetic": ins.is_synthetic,
                "created_at": ins.created_at.isoformat() if ins.created_at else None,
            }
            for ins in (insights or [])
        ],
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ---------------------------------------------------------------------------
# Access Control Helper
# ---------------------------------------------------------------------------

async def _get_study_and_verify_access(
    study_id: str,
    session: AsyncSession,
    user: Optional[Users] = None,
    *,
    write: bool = False,
) -> Studies:
    """Verify study existence and enforce strict multi-tenant ownership.

    ``write=True`` selects the strict write predicate: the ``is_demo`` read
    allowance must never let a non-owner mutate the shared demo.
    """
    res = await session.execute(select(Studies).where(Studies.id == study_id))
    study = res.scalar_one_or_none()
    if not study:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Study with id '{study_id}' not found.",
        )
    predicate = user_can_write_study if write else user_owns_study
    if not predicate(study, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have access to this study's behavioral tests.",
        )
    return study


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/studies/{study_id}/behavioral-tests", status_code=status.HTTP_201_CREATED)
async def create_behavioral_test(
    study_id: str,
    payload: CreateBehavioralTestRequest,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Create a new behavioral test and its initial scenario."""
    await _get_study_and_verify_access(study_id, session, user, write=True)

    # Validate the researcher's own words BEFORE any row is staged.
    scenario_title = payload.scenario_title or payload.name
    scenario_text = (payload.scenario_text or payload.description or "").strip()
    if not scenario_text:
        raise APIError(
            400,
            "Describe the scenario the personas should react to (scenario_text or description).",
            error_code="scenario_required",
        )

    test_id = f"bt_{uuid.uuid4().hex[:16]}"
    user_id = user.id if user else None

    test = BehavioralTests(
        id=test_id,
        study_id=study_id,
        user_id=user_id,
        name=payload.name,
        description=payload.description,
        test_type=payload.test_type,
        configuration=payload.configuration or {},
        status="ready",
    )
    session.add(test)
    # No relationship() links these mappers, so the unit of work orders their
    # INSERTs alphabetically (scenarios before tests) and Postgres rejected the
    # child row's FK. Flushing the parent first makes the order explicit.
    await session.flush()

    scenario = BehavioralTestScenarios(
        id=f"bts_{uuid.uuid4().hex[:16]}",
        behavioral_test_id=test_id,
        title=scenario_title,
        scenario_text=scenario_text,
        structured_parameters=payload.configuration or {},
    )
    session.add(scenario)

    await session.commit()
    return _serialize_test(test, scenarios=[scenario], runs=[])


@router.get("/studies/{study_id}/behavioral-tests")
async def list_behavioral_tests(
    study_id: str,
    q: Optional[str] = Query(default=None),
    test_type: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> list[dict[str, Any]]:
    """List behavioral tests for a study with optional search and type filtering."""
    await _get_study_and_verify_access(study_id, session, user)

    query = (
        select(BehavioralTests)
        .where(BehavioralTests.study_id == study_id)
        .where(_read_owner(BehavioralTests.user_id, user))
        .order_by(BehavioralTests.created_at.desc())
    )

    if test_type and test_type != "all":
        query = query.where(BehavioralTests.test_type == test_type)
    if status_filter and status_filter != "all":
        query = query.where(BehavioralTests.status == status_filter)

    res = await session.execute(query)
    tests = res.scalars().all()

    if q:
        q_lower = q.lower()
        tests = [t for t in tests if q_lower in t.name.lower() or (t.description and q_lower in t.description.lower())]

    output: list[dict[str, Any]] = []
    for t in tests:
        # Load scenarios
        res_scenarios = await session.execute(
            select(BehavioralTestScenarios)
            .where(BehavioralTestScenarios.behavioral_test_id == t.id)
            .order_by(BehavioralTestScenarios.created_at.asc())
        )
        scenarios = res_scenarios.scalars().all()

        # Load runs
        res_runs = await session.execute(
            select(BehavioralTestRuns)
            .where(BehavioralTestRuns.behavioral_test_id == t.id)
            .where(_read_owner(BehavioralTestRuns.user_id, user))
            .order_by(BehavioralTestRuns.created_at.desc())
        )
        runs = res_runs.scalars().all()

        output.append(_serialize_test(t, scenarios=scenarios, runs=runs))

    return output


@router.get("/studies/{study_id}/behavioral-tests/metrics")
async def get_behavioral_metrics(
    study_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get aggregate top-level behavioral testing statistics for a study."""
    await _get_study_and_verify_access(study_id, session, user)

    res_tests = await session.execute(
        select(func.count(BehavioralTests.id)).where(BehavioralTests.study_id == study_id, _read_owner(BehavioralTests.user_id, user))
    )
    total_tests = res_tests.scalar_one() or 0

    res_runs = await session.execute(
        select(BehavioralTestRuns).where(BehavioralTestRuns.study_id == study_id, _read_owner(BehavioralTestRuns.user_id, user))
    )
    runs = res_runs.scalars().all()

    completed_runs = sum(1 for r in runs if r.status in ("completed", "completed_with_warnings"))
    total_personas_simulated = sum(r.completed_count for r in runs)

    probabilities = [
        (r.aggregate_metrics or {}).get("average_likelihood", 0.5)
        for r in runs
        if (r.aggregate_metrics or {}).get("average_likelihood") is not None
    ]
    avg_buy_likelihood = round(sum(probabilities) / len(probabilities), 2) if probabilities else 0.52

    return {
        "study_id": study_id,
        "total_tests": total_tests,
        "total_runs": len(runs),
        "completed_runs": completed_runs,
        "total_personas_simulated": total_personas_simulated,
        "average_buy_likelihood": avg_buy_likelihood,
        "average_buy_likelihood_percentage": int(avg_buy_likelihood * 100),
    }


# Registered BEFORE `/behavioral-tests/{test_id}`: Starlette matches routes in
# declaration order, so a literal segment declared after a sibling `{param}`
# route is unreachable (this one used to 404 as "test 'compare' not found").
@router.get("/studies/{study_id}/behavioral-tests/compare")
async def compare_behavioral_runs(
    study_id: str,
    run_ids: str = Query(default="", description="Comma-separated run IDs to compare"),
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Compare multiple historical simulation runs side-by-side."""
    await _get_study_and_verify_access(study_id, session, user)

    ids = [i.strip() for i in run_ids.split(",") if i.strip()]
    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one run_id must be provided for comparison.",
        )

    res = await session.execute(
        select(BehavioralTestRuns).where(
            BehavioralTestRuns.id.in_(ids),
            BehavioralTestRuns.study_id == study_id,
            _read_owner(BehavioralTestRuns.user_id, user),
        )
    )
    runs = res.scalars().all()

    compared_runs: list[dict[str, Any]] = []
    for r in runs:
        res_results = await session.execute(
            select(BehavioralTestResults).where(BehavioralTestResults.test_run_id == r.id)
        )
        results = res_results.scalars().all()
        compared_runs.append(_serialize_run(r, results=results))

    return {
        "study_id": study_id,
        "compared_run_count": len(compared_runs),
        "runs": compared_runs,
    }


@router.get("/studies/{study_id}/behavioral-tests/{test_id}")
async def get_behavioral_test_detail(
    study_id: str,
    test_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get single behavioral test detail with scenarios and runs history."""
    await _get_study_and_verify_access(study_id, session, user)

    res = await session.execute(
        select(BehavioralTests).where(
            BehavioralTests.id == test_id,
            BehavioralTests.study_id == study_id,
            _read_owner(BehavioralTests.user_id, user),
        )
    )
    test = res.scalar_one_or_none()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test '{test_id}' not found.",
        )

    res_scenarios = await session.execute(
        select(BehavioralTestScenarios)
        .where(BehavioralTestScenarios.behavioral_test_id == test_id)
        .order_by(BehavioralTestScenarios.created_at.asc())
    )
    scenarios = res_scenarios.scalars().all()

    res_runs = await session.execute(
        select(BehavioralTestRuns)
        .where(BehavioralTestRuns.behavioral_test_id == test_id)
        .where(_read_owner(BehavioralTestRuns.user_id, user))
        .order_by(BehavioralTestRuns.created_at.desc())
    )
    runs = res_runs.scalars().all()

    return _serialize_test(test, scenarios=scenarios, runs=runs)


@router.put("/studies/{study_id}/behavioral-tests/{test_id}")
async def update_behavioral_test(
    study_id: str,
    test_id: str,
    payload: UpdateBehavioralTestRequest,
    session: AsyncSession = Depends(get_session),
    user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    """Update behavioral test configuration or scenario."""
    await _get_study_and_verify_access(study_id, session, user, write=True)

    res = await session.execute(
        select(BehavioralTests).where(
            BehavioralTests.id == test_id,
            BehavioralTests.study_id == study_id,
            BehavioralTests.user_id == user.id,
        )
    )
    test = res.scalar_one_or_none()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test '{test_id}' not found.",
        )

    if payload.name is not None:
        test.name = payload.name
    if payload.description is not None:
        test.description = payload.description
    if payload.test_type is not None:
        test.test_type = payload.test_type
    if payload.configuration is not None:
        test.configuration = payload.configuration
    if payload.status is not None:
        test.status = payload.status

    if payload.scenario_title or payload.scenario_text:
        res_sc = await session.execute(
            select(BehavioralTestScenarios).where(BehavioralTestScenarios.behavioral_test_id == test_id)
        )
        scenario = res_sc.scalars().first()
        if scenario:
            if payload.scenario_title:
                scenario.title = payload.scenario_title
            if payload.scenario_text:
                scenario.scenario_text = payload.scenario_text
            if payload.configuration:
                scenario.structured_parameters = payload.configuration

    await session.commit()
    return await get_behavioral_test_detail(study_id, test_id, session, user)


@router.delete("/studies/{study_id}/behavioral-tests/{test_id}")
async def delete_behavioral_test(
    study_id: str,
    test_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Archive a behavioral test."""
    await _get_study_and_verify_access(study_id, session, user, write=True)

    res = await session.execute(
        select(BehavioralTests).where(
            BehavioralTests.id == test_id,
            BehavioralTests.study_id == study_id,
        )
    )
    test = res.scalar_one_or_none()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test '{test_id}' not found.",
        )

    test.status = "archived"
    await session.commit()
    return {"message": "Behavioral test archived", "id": test_id}


# ---------------------------------------------------------------------------
# Test Runs & Execution
# ---------------------------------------------------------------------------

@router.post("/studies/{study_id}/behavioral-tests/{test_id}/runs", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def trigger_behavioral_test_run(
    study_id: str,
    test_id: str,
    payload: RunBehavioralTestRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: Users = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=200),
) -> dict[str, Any]:
    """Trigger a new simulation run across target personas."""
    await _get_study_and_verify_access(study_id, session, user, write=True)

    res_test = await session.execute(
        select(BehavioralTests).where(
            BehavioralTests.id == test_id,
            BehavioralTests.study_id == study_id,
        )
    )
    test = res_test.scalar_one_or_none()
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test '{test_id}' not found.",
        )
    if user is None or test.owner_id != user.id:
        raise APIError(404, "Behavioral test not found.", error_code="not_found")
    verified_owner = user.id

    # Determine scenario snapshot — only the researcher's own text: the body's
    # scenario, the stored scenario the body names, the test's most recent stored
    # scenario, or the test description. Found live: create() stores the scenario
    # in behavioral_test_scenarios, but run() read only test.description, so a
    # test created with scenario_text alone could never be run (400).
    scenario_row: Optional[BehavioralTestScenarios] = None
    if payload.scenario_id or not (payload.scenario_text or "").strip():
        scenario_q = select(BehavioralTestScenarios).where(
            BehavioralTestScenarios.behavioral_test_id == test_id
        )
        if payload.scenario_id:
            scenario_q = scenario_q.where(BehavioralTestScenarios.id == payload.scenario_id)
        scenario_row = (
            await session.execute(scenario_q.order_by(BehavioralTestScenarios.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if payload.scenario_id and scenario_row is None:
            # The caller named a scenario; running a different text under its
            # id would report results for a scenario nobody chose.
            raise APIError(
                404,
                f"Scenario '{payload.scenario_id}' does not belong to this test.",
                error_code="scenario_not_found",
            )
    scenario_text = (
        payload.scenario_text
        or (scenario_row.scenario_text if scenario_row else None)
        or test.description
        or ""
    ).strip()
    if not scenario_text:
        raise APIError(
            400,
            "This test has no scenario text; add scenario_text before running it.",
            error_code="scenario_required",
        )
    scenario_snapshot = {
        "title": payload.scenario_title or (scenario_row.title if scenario_row else None) or test.name,
        "scenario_text": scenario_text,
        "structured_parameters": payload.parameters
        or (scenario_row.structured_parameters if scenario_row else None)
        or test.configuration
        or {},
        "test_type": test.test_type,
    }
    try:
        RunBehavioralTestRequest(
            scenario_title=scenario_snapshot["title"], scenario_text=scenario_text,
            parameters=scenario_snapshot["structured_parameters"],
        )
    except ValidationError as exc:
        raise APIError(422, "The stored scenario exceeds the supported input limits.", error_code="behavioral_scenario_invalid") from exc

    # Count personas
    if payload.target_population_type == "selected_personas" and not payload.target_persona_ids:
        raise APIError(422, "Select at least one persona.", error_code="behavioral_population_required")
    if payload.target_population_type == "segment" and not payload.target_segment_id:
        raise APIError(422, "Select a segment.", error_code="behavioral_population_required")
    target_persona_ids = payload.target_persona_ids or []
    if payload.target_population_type == "segment" and payload.target_segment_id:
        res_p = await session.execute(
            select(Personas.id).where(
                Personas.study_id == study_id,
                Personas.segment_id == payload.target_segment_id,
            )
        )
        target_persona_ids = [p[0] for p in res_p.all()]
    elif payload.target_population_type == "all" or not target_persona_ids:
        res_p = await session.execute(select(Personas.id).where(Personas.study_id == study_id))
        target_persona_ids = [p[0] for p in res_p.all()]
    else:
        # Client-supplied ids: constrain to this study or a caller could
        # simulate — and read back — another tenant's personas.
        res_p = await session.execute(
            select(Personas.id).where(
                Personas.id.in_(target_persona_ids),
                Personas.study_id == study_id,
            )
        )
        resolved = [p[0] for p in res_p.all()]
        if len(resolved) != len(set(target_persona_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more target personas do not belong to this study.",
            )
        target_persona_ids = resolved

    if not target_persona_ids:
        raise APIError(
            400,
            "This study has no personas to simulate. Generate personas first; BebshaX does not simulate invented respondents.",
            error_code="behavioral_requires_personas",
        )
    if len(target_persona_ids) > 50:
        raise APIError(422, "A behavioral run supports at most 50 personas.", error_code="behavioral_population_limit")

    captured_personas = (await session.execute(select(Personas.id, Personas.version).where(
        Personas.id.in_(target_persona_ids), Personas.study_id == study_id, Personas.owner_id == verified_owner,
    ).order_by(Personas.id))).all()
    persona_manifest = [{"id": persona_id, "version": version} for persona_id, version in captured_personas]
    if len(persona_manifest) != len(set(target_persona_ids)):
        raise APIError(409, "The target population is not owned by you.", error_code="behavioral_population_changed")
    test_revision = test.updated_at.isoformat() if test.updated_at else None
    scenario_revision = scenario_row.updated_at.isoformat() if scenario_row and scenario_row.updated_at else None
    revision_manifest = {"personas": persona_manifest, "test_revision": test_revision, "scenario_revision": scenario_revision}

    engine: Optional[BehavioralSimulationEngine] = getattr(request.app.state, "behavioral_engine", None)
    if engine is None:
        llm = getattr(request.app.state, "llm_router", None)
        sm = getattr(request.app.state, "db_sessionmaker", None)
        if llm and sm:
            engine = BehavioralSimulationEngine(llm, sm, memory=getattr(request.app.state, "memory_service", None))
    if engine is None:
        # Never create a run that nothing will execute.
        raise LLMUnavailable("Behavioral simulation")

    run_id = f"btr_{uuid.uuid4().hex[:16]}"
    scenario_id = scenario_row.id if scenario_row else None
    await session.rollback()

    async def prepare(db_session: AsyncSession, job: dict[str, Any]) -> dict[str, Any]:
        owned_study = await db_session.scalar(select(Studies).where(Studies.id == study_id, Studies.user_id == verified_owner).with_for_update())
        owned_test = await db_session.scalar(select(BehavioralTests).where(
            BehavioralTests.id == test_id, BehavioralTests.study_id == study_id, BehavioralTests.user_id == verified_owner,
        ).with_for_update())
        if owned_study is None or owned_test is None:
            raise APIError(404, "Behavioral test not found.", error_code="not_found")
        if (owned_test.updated_at.isoformat() if owned_test.updated_at else None) != test_revision:
            raise APIError(409, "The behavioral test changed before admission.", error_code="behavioral_input_changed")
        if scenario_id is not None:
            current_scenario = await db_session.scalar(select(BehavioralTestScenarios).where(
                BehavioralTestScenarios.id == scenario_id, BehavioralTestScenarios.behavioral_test_id == test_id,
            ).with_for_update())
            if current_scenario is None or (current_scenario.updated_at.isoformat() if current_scenario.updated_at else None) != scenario_revision:
                raise APIError(409, "The scenario changed before admission.", error_code="behavioral_input_changed")
        captured = (await db_session.execute(select(Personas.id, Personas.version).where(
            Personas.id.in_(target_persona_ids), Personas.study_id == study_id, Personas.owner_id == verified_owner,
        ).order_by(Personas.id))).all()
        if [{"id": persona_id, "version": version} for persona_id, version in captured] != persona_manifest:
            raise APIError(409, "The target persona population changed or is not owned by you.", error_code="behavioral_population_changed")
        db_session.add(BehavioralTestRuns(
            id=run_id, behavioral_test_id=test_id, study_id=study_id, user_id=verified_owner,
            job_id=job["job_id"], scenario_id=scenario_id, scenario_snapshot=scenario_snapshot,
            input_manifest={"personas": persona_manifest, "test_type": scenario_snapshot["test_type"]},
            target_population_type=payload.target_population_type, target_segment_id=payload.target_segment_id,
            target_persona_ids=target_persona_ids, status="pending", persona_count=len(target_persona_ids),
            completed_count=0, failed_count=0,
        ))
        return {"run_id": run_id}

    async def runner(job: JobContext) -> None:
        completed = await engine.execute_test_run(run_id=job["result_refs"]["run_id"], user_id=verified_owner, job=job)
        job["result"] = _serialize_run(completed)

    job = await start_job_async(
        request.app, kind="behavioral_simulation", scope_id=study_id, user_id=verified_owner,
        runner=runner, input_data={"test_id": test_id, "request": payload.model_dump(), "scenario": scenario_snapshot, "revision": revision_manifest},
        input_revision=input_snapshot(revision_manifest)[1], idempotency_key=idempotency_key, prepare=prepare,
    )
    run = await session.get(BehavioralTestRuns, job["result_refs"]["run_id"])
    if run is None:
        raise APIError(404, "Behavioral run no longer exists.", error_code="not_found")
    return _serialize_run(run)


@router.get("/studies/{study_id}/behavioral-tests/{test_id}/runs")
async def list_behavioral_test_runs(
    study_id: str,
    test_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> list[dict[str, Any]]:
    """List historical simulation runs for a behavioral test."""
    await _get_study_and_verify_access(study_id, session, user)

    res = await session.execute(
        select(BehavioralTestRuns)
        .where(
            BehavioralTestRuns.behavioral_test_id == test_id,
            BehavioralTestRuns.study_id == study_id,
            _read_owner(BehavioralTestRuns.user_id, user),
        )
        .order_by(BehavioralTestRuns.created_at.desc())
    )
    runs = res.scalars().all()
    return [_serialize_run(r) for r in runs]


@router.get("/studies/{study_id}/behavioral-tests/runs/{run_id}")
async def get_behavioral_run_status(
    study_id: str,
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get single simulation run status, live progress, and results."""
    await _get_study_and_verify_access(study_id, session, user)

    res = await session.execute(
        select(BehavioralTestRuns).where(
            BehavioralTestRuns.id == run_id,
            BehavioralTestRuns.study_id == study_id,
        )
    )
    run = res.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test run '{run_id}' not found.",
        )
    if run.user_id is not None and (user is None or run.user_id != user.id):
        raise APIError(404, "Behavioral test run not found.", error_code="not_found")
    job = None
    if request is not None and run.job_id and user is not None and run.user_id == user.id:
        run_job_id = run.job_id
        await session.rollback()
        job = await get_job_async(request.app, run_job_id, kind="behavioral_simulation", scope_id=study_id, user_id=user.id)
        if job is not None and job["status"] == "failed":
            await session.execute(update(BehavioralTestRuns).where(
                BehavioralTestRuns.id == run_id, BehavioralTestRuns.job_id == run_job_id,
                BehavioralTestRuns.user_id == user.id,
                BehavioralTestRuns.status.in_(("pending", "running", "retry_pending")),
            ).values(status="cancelled" if job["state"] == "cancelled" else "failed", error_message=job["error"], completed_at=_utcnow(), execution_token=None))
            await session.commit()
        run = await session.get(BehavioralTestRuns, run_id, populate_existing=True)
        if run is None:
            raise APIError(404, "Behavioral test run not found.", error_code="not_found")

    res_results = await session.execute(
        select(BehavioralTestResults)
        .where(BehavioralTestResults.test_run_id == run_id)
        .order_by(BehavioralTestResults.probability.desc())
    )
    results = res_results.scalars().all()

    res_insights = await session.execute(
        select(BehavioralInsights)
        .where(BehavioralInsights.test_run_id == run_id)
        .order_by(BehavioralInsights.created_at.desc())
    )
    insights = res_insights.scalars().all()

    response = _serialize_run(run, results=results, insights=insights)
    if job is not None:
        response["job_state"] = job["state"]
        response["job_error_code"] = job["error_code"]
        response["provider_outcome_unknown"] = job["provider_outcome_unknown"]
        response["checkpoints"] = job["checkpoints"]
    return response


@router.get("/studies/{study_id}/behavioral-tests/runs/{run_id}/results")
async def get_behavioral_run_results(
    study_id: str,
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get full structured results and breakdown for a simulation run."""
    return await get_behavioral_run_status(study_id, run_id, request, session, user)


@router.post("/studies/{study_id}/behavioral-tests/runs/{run_id}/retry-failed", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def retry_failed_simulations(
    study_id: str,
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: Users = Depends(get_current_user),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=200),
) -> dict[str, Any]:
    """Retry only failed persona simulations in a run."""
    await _get_study_and_verify_access(study_id, session, user, write=True)

    # Child-parent check: the engine loads the run by id alone, so without this
    # a caller who legitimately owns `study_id` could re-execute — and
    # overwrite — another tenant's run.
    owned_run = (
        await session.execute(
            select(BehavioralTestRuns).where(
                BehavioralTestRuns.id == run_id,
                BehavioralTestRuns.study_id == study_id,
            )
        )
    ).scalar_one_or_none()
    if not owned_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Behavioral test run '{run_id}' not found.",
        )
    if user is None or owned_run.user_id != user.id:
        raise APIError(404, "Behavioral test run not found.", error_code="not_found")
    verified_owner = user.id

    engine: Optional[BehavioralSimulationEngine] = getattr(request.app.state, "behavioral_engine", None)
    if engine is None:
        llm = getattr(request.app.state, "llm_router", None)
        sm = getattr(request.app.state, "db_sessionmaker", None)
        if llm and sm:
            engine = BehavioralSimulationEngine(llm, sm, memory=getattr(request.app.state, "memory_service", None))

    if not engine:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Behavioral engine is not configured.",
        )

    retry_input = {
        "run_id": run_id, "operation": "retry_failed", "scenario": owned_run.scenario_snapshot,
        "input_manifest": owned_run.input_manifest, "persona_ids": owned_run.target_persona_ids,
    }
    await session.rollback()

    async def prepare(db_session: AsyncSession, job: dict[str, Any]) -> dict[str, Any]:
        parent = await db_session.scalar(select(Studies).where(Studies.id == study_id, Studies.user_id == verified_owner).with_for_update())
        current = await db_session.scalar(select(BehavioralTestRuns).where(
            BehavioralTestRuns.id == run_id, BehavioralTestRuns.study_id == study_id, BehavioralTestRuns.user_id == verified_owner,
        ).with_for_update())
        if parent is None or current is None:
            raise APIError(404, "Behavioral test run not found.", error_code="not_found")
        if current.status in {"pending", "running", "retry_pending"}:
            raise APIError(409, "This behavioral run is already executing.", error_code="behavioral_run_active")
        current.status, current.job_id = "retry_pending", job["job_id"]
        current.execution_token = None
        return {"run_id": run_id}

    async def runner(job: JobContext) -> None:
        completed = await engine.retry_failed_simulations(run_id, study_id=study_id, user_id=verified_owner, job=job)
        job["result"] = _serialize_run(completed)

    job = await start_job_async(
        request.app, kind="behavioral_simulation", scope_id=study_id, user_id=verified_owner,
        input_data=retry_input, input_revision=input_snapshot(retry_input)[1], idempotency_key=idempotency_key,
        runner=runner, prepare=prepare,
    )
    current = await session.get(BehavioralTestRuns, run_id)
    if current is None:
        raise APIError(404, "Behavioral run no longer exists.", error_code="not_found")
    response = _serialize_run(current)
    response["job_id"] = job["job_id"]
    return response


@router.post("/studies/{study_id}/behavioral-tests/runs/{run_id}/cancel")
@limiter.limit("30/minute")
async def cancel_behavioral_run(
    study_id: str, run_id: str, request: Request,
    session: AsyncSession = Depends(get_session), user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    await _get_study_and_verify_access(study_id, session, user, write=True)
    run = await session.scalar(select(BehavioralTestRuns).where(
        BehavioralTestRuns.id == run_id, BehavioralTestRuns.study_id == study_id, BehavioralTestRuns.user_id == user.id,
    ))
    if run is None:
        raise APIError(404, "Behavioral test run not found.", error_code="not_found")
    if not run.job_id:
        was_running = run.status in {"running", "retry_pending"}
        await session.execute(update(BehavioralTestRuns).where(
            BehavioralTestRuns.id == run_id, BehavioralTestRuns.study_id == study_id,
            BehavioralTestRuns.user_id == user.id, BehavioralTestRuns.job_id.is_(None),
            BehavioralTestRuns.status.in_(("pending", "running", "retry_pending")),
        ).values(status="cancelled", execution_token=None, completed_at=_utcnow(),
                 error_message="Legacy execution cancelled; any external request outcome remains unknown."))
        await session.commit()
        run = await session.get(BehavioralTestRuns, run_id, populate_existing=True)
        if run is None:
            raise APIError(404, "Behavioral test run not found.", error_code="not_found")
        response = _serialize_run(run)
        response["provider_outcome_unknown"] = was_running
        return response
    run_job_id = run.job_id
    await session.rollback()
    job = await cancel_job_async(request.app, run_job_id, kind="behavioral_simulation", scope_id=study_id, user_id=user.id)
    if job is None:
        raise APIError(404, "Behavioral job not found.", error_code="not_found")
    if job["status"] == "failed":
        await session.execute(update(BehavioralTestRuns).where(
            BehavioralTestRuns.id == run_id, BehavioralTestRuns.study_id == study_id,
            BehavioralTestRuns.user_id == user.id, BehavioralTestRuns.job_id == run_job_id,
            BehavioralTestRuns.status.in_(("pending", "running", "retry_pending")),
        ).values(status="cancelled" if job["state"] == "cancelled" else "failed", error_message=job["error"], completed_at=_utcnow(), execution_token=None))
        await session.commit()
    run = await session.get(BehavioralTestRuns, run_id, populate_existing=True)
    if run is None:
        raise APIError(404, "Behavioral test run not found.", error_code="not_found")
    response = _serialize_run(run)
    response["job_state"] = job["state"]
    return response
