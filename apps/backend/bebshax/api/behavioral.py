"""Behavioral Testing REST API: study-scoped simulation creation, batch execution, live progress, and results."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_optional_current_user
from bebshax.api.deps import get_session, user_can_write_study, user_owns_study
from bebshax.api.limiter import limiter
from bebshax.auth.models import Users
from bebshax.behavioral.engine import BehavioralRunNotFound, BehavioralSimulationEngine, BehavioralTestNotFound
from bebshax.behavioral.orm import (
    BehavioralInsights,
    BehavioralTestResults,
    BehavioralTestRuns,
    BehavioralTestScenarios,
    BehavioralTests,
)
from bebshax.db.models import Personas, Studies
from bebshax.llm.failures import LLMError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["behavioral-testing"])

# asyncio only keeps weak references to tasks: an un-referenced run task could
# be garbage-collected mid-simulation. Strong refs live here until done.
_RUN_TASKS: set[asyncio.Task] = set()


def _track_run_task(task: asyncio.Task, run_id: str) -> None:
    _RUN_TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _RUN_TASKS.discard(t)
        if t.cancelled():
            logger.warning("behavioral run %s task cancelled", run_id)
            return
        exc = t.exception()
        if exc is not None:
            # The engine already persisted the failure and logged the traceback;
            # this is the one-line marker that the task itself ended in error.
            logger.error("behavioral run %s task failed: %s", run_id, type(exc).__name__)

    task.add_done_callback(_done)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    scenario_title: Optional[str] = None
    scenario_text: Optional[str] = None


class RunBehavioralTestRequest(BaseModel):
    scenario_id: Optional[str] = None
    scenario_title: Optional[str] = None
    scenario_text: Optional[str] = None
    parameters: Optional[dict] = None
    target_population_type: str = Field(default="all", pattern="^(all|segment|selected_personas)$")
    target_segment_id: Optional[str] = None
    target_persona_ids: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_test(t: BehavioralTests, scenarios: Optional[list[BehavioralTestScenarios]] = None, runs: Optional[list[BehavioralTestRuns]] = None) -> dict[str, Any]:
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


def _serialize_run(r: BehavioralTestRuns, results: Optional[list[BehavioralTestResults]] = None, insights: Optional[list[BehavioralInsights]] = None) -> dict[str, Any]:
    return {
        "id": r.id,
        "behavioral_test_id": r.behavioral_test_id,
        "study_id": r.study_id,
        "scenario_id": r.scenario_id,
        "scenario_snapshot": r.scenario_snapshot or {},
        "target_population_type": r.target_population_type,
        "target_segment_id": r.target_segment_id,
        "target_persona_ids": r.target_persona_ids or [],
        "status": r.status,
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

    # Initial scenario
    scenario_title = payload.scenario_title or payload.name
    scenario_text = payload.scenario_text or payload.description or f"Evaluate {payload.test_type.replace('_', ' ')}"
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
        select(func.count(BehavioralTests.id)).where(BehavioralTests.study_id == study_id)
    )
    total_tests = res_tests.scalar_one() or 0

    res_runs = await session.execute(
        select(BehavioralTestRuns).where(BehavioralTestRuns.study_id == study_id)
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
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Update behavioral test configuration or scenario."""
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
    user: Optional[Users] = Depends(get_optional_current_user),
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

    # Determine scenario snapshot
    scenario_snapshot = {
        "title": payload.scenario_title or test.name,
        "scenario_text": payload.scenario_text or test.description or f"Evaluate {test.test_type}",
        "structured_parameters": payload.parameters or test.configuration or {},
    }

    # Count personas
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

    run_id = f"btr_{uuid.uuid4().hex[:16]}"
    run = BehavioralTestRuns(
        id=run_id,
        behavioral_test_id=test_id,
        study_id=study_id,
        user_id=user.id if user else None,
        scenario_id=payload.scenario_id,
        scenario_snapshot=scenario_snapshot,
        target_population_type=payload.target_population_type,
        target_segment_id=payload.target_segment_id,
        target_persona_ids=target_persona_ids,
        status="pending",
        persona_count=len(target_persona_ids),
        completed_count=0,
        failed_count=0,
    )
    session.add(run)
    await session.commit()

    engine: Optional[BehavioralSimulationEngine] = getattr(request.app.state, "behavioral_engine", None)
    if engine is None:
        llm = getattr(request.app.state, "llm_router", None)
        sm = getattr(request.app.state, "db_sessionmaker", None)
        if llm and sm:
            engine = BehavioralSimulationEngine(llm, sm)

    if engine:
        _track_run_task(
            asyncio.create_task(
                engine.execute_test_run(run_id=run_id, user_id=user.id if user else None)
            ),
            run_id,
        )

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
        )
        .order_by(BehavioralTestRuns.created_at.desc())
    )
    runs = res.scalars().all()
    return [_serialize_run(r) for r in runs]


@router.get("/studies/{study_id}/behavioral-tests/runs/{run_id}")
async def get_behavioral_run_status(
    study_id: str,
    run_id: str,
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

    return _serialize_run(run, results=results, insights=insights)


@router.get("/studies/{study_id}/behavioral-tests/runs/{run_id}/results")
async def get_behavioral_run_results(
    study_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Get full structured results and breakdown for a simulation run."""
    return await get_behavioral_run_status(study_id, run_id, session, user)


@router.post("/studies/{study_id}/behavioral-tests/runs/{run_id}/retry-failed")
@limiter.limit("10/minute")
async def retry_failed_simulations(
    study_id: str,
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: Optional[Users] = Depends(get_optional_current_user),
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

    engine: Optional[BehavioralSimulationEngine] = getattr(request.app.state, "behavioral_engine", None)
    if engine is None:
        llm = getattr(request.app.state, "llm_router", None)
        sm = getattr(request.app.state, "db_sessionmaker", None)
        if llm and sm:
            engine = BehavioralSimulationEngine(llm, sm)

    if not engine:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Behavioral engine is not configured.",
        )

    try:
        updated_run = await engine.retry_failed_simulations(run_id, study_id=study_id)
        return await get_behavioral_run_status(study_id, run_id, session, user)
    except LLMError:
        # Routing failures keep their classified envelope (503 all_candidates_failed /
        # 413 context_window_exceeded with attempts) via the global handlers.
        raise
    except Exception:
        logger.error("behavioral retry failed for run %s", run_id, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Retry failed. Please try again.",
        )
