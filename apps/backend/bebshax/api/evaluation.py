"""Evaluation and insights REST API endpoints (Phase 11, M1 rewrite).

Every number here is measured — aggregated from persisted provenance
(`llm_requests`), persona validation artifacts, or the judged quality-gate
reports written by scripts/judge_local_interview.py. Metrics with no
underlying data are `null`, never an invented 0.0 or 1.0 (M1: the audited
endpoint fabricated a "ROUND_ROBIN (Naive)" comparison arm with multiplier
fiction and asserted perfect schema validity).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Request
from sqlalchemy import select, func

from bebshax.db.models import Personas, LLMRequests
from bebshax.llm.failures import FailureKind
from bebshax.llm.pools import OLLAMA
from bebshax.llm.types import TaskType
from bebshax.persona.orm import PersonaAttributes, PersonaDetails

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evaluation"])

# Newest-first bound on the Python-side llm_requests scan below — keeps the
# metrics endpoint O(bounded) as provenance history grows.
_METRICS_SCAN_LIMIT = 5000

# Judged A/B gate reports (scripts/judge_local_interview.py). CWD-relative to
# the repo root like evaluation/report_generator.py; overridable for tests
# and deployments.
_GATE_GLOB = "local_3b_gate_*.json"


def _metadata_dir() -> Path:
    return Path(os.environ.get("BEBSHAX_METADATA_DIR", "data/metadata"))


def _load_latest_quality_gate() -> Optional[dict[str, Any]]:
    """Summarize the newest READABLE judged quality-gate report, or None."""
    try:
        candidates = sorted(_metadata_dir().glob(_GATE_GLOB))
    except OSError:
        return None
    # Newest first; a corrupt newest file must not hide older valid reports.
    for latest in reversed(candidates):
        try:
            raw = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("quality gate report unreadable: %s", latest.name, exc_info=True)
            continue
        if not isinstance(raw, dict):
            logger.warning("quality gate report has wrong shape: %s", latest.name)
            continue
        arms = []
        for key in ("arm_a", "arm_b"):
            arm = raw.get(key)
            arm = arm if isinstance(arm, dict) else {}
            arms.append(
                {
                    "tag": arm.get("tag"),
                    "model": arm.get("model"),
                    "weighted_score": arm.get("weighted"),
                    "avg_latency_ms": arm.get("avg_ms"),
                    "dims": arm.get("dims"),
                }
            )
        judge = raw.get("judge")
        judge = judge if isinstance(judge, dict) else {}
        return {
            "generated_at": raw.get("generated_at"),
            "bar": raw.get("bar"),
            "rubric_weights": raw.get("rubric_weights"),
            "arms": arms,
            "judge_route": judge.get("route"),
            "judge_notes": judge.get("notes"),
            "source_file": latest.name,
        }
    return None


@router.get("/evaluation/metrics")
async def get_evaluation_metrics(request: Request) -> dict[str, Any]:
    """Persona synthesis health + measured per-pool routing performance.

    Contract (all measured, `null` = no data yet):
    - overall_health: persona counts, provenance-derived schema validity,
      consistency pass rate over evaluable personas, grounding ratio,
      average request latency.
    - pools: one row per pool actually present in llm_requests — success
      rate, latency, fallback rate (multi-attempt requests), and the share
      served by the local ollama adapter.
    - quality_gate: latest judged local-vs-cloud interview gate, if any.
    """
    sessionmaker_ = getattr(request.app.state, "db_sessionmaker", None)

    total_personas = 0
    avg_latency: Optional[float] = None
    avg_grounding_ratio: Optional[float] = None
    consistency_pass_rate: Optional[float] = None
    schema_validity_rate: Optional[float] = None
    pools: list[dict[str, Any]] = []

    if sessionmaker_:
        async with sessionmaker_() as session:
            total_personas = (
                await session.execute(select(func.count(Personas.id)))
            ).scalar_one_or_none() or 0

            # Grounding: OBSERVED attributes / all attributes (provenance classes).
            total_attrs = (
                await session.execute(select(func.count(PersonaAttributes.id)))
            ).scalar_one_or_none() or 0
            if total_attrs > 0:
                observed_attrs = (
                    await session.execute(
                        select(func.count(PersonaAttributes.id)).where(
                            PersonaAttributes.provenance_class == "OBSERVED"
                        )
                    )
                ).scalar_one_or_none() or 0
                avg_grounding_ratio = round(observed_attrs / total_attrs, 3)

            # Consistency: personas whose stored validation produced 0 warnings,
            # over the personas that HAVE validation details. No details rows →
            # nothing evaluable → null (never a claimed-perfect 1.0).
            details_list = (await session.execute(select(PersonaDetails))).scalars().all()
            if details_list:
                passed = sum(1 for d in details_list if not d.warnings)
                consistency_pass_rate = round(passed / len(details_list), 3)

            # Request-level aggregates from provenance. Only the columns we
            # aggregate — attempts JSON is needed for fallback/malformed counts.
            # TODO(perf): attempts-JSON inspection keeps this in Python; move
            # counts/latency to SQL GROUP BY when that changes. Mitigated for
            # now by bounding the scan to the newest _METRICS_SCAN_LIMIT rows
            # (metrics are honest over that window; dev-scale DBs sit far
            # below it, so numbers are unchanged there).
            rows = (
                await session.execute(
                    select(
                        LLMRequests.task,
                        LLMRequests.pool,
                        LLMRequests.success,
                        LLMRequests.total_latency_ms,
                        LLMRequests.attempts,
                        LLMRequests.served_by_provider,
                    )
                    .order_by(LLMRequests.created_at.desc())
                    .limit(_METRICS_SCAN_LIMIT)
                )
            ).all()

            latencies = [r.total_latency_ms for r in rows if r.total_latency_ms is not None]
            if latencies:
                avg_latency = round(sum(latencies) / len(latencies), 1)

            # Schema validity, measured from the failure taxonomy (R6): the
            # share of persona-generation requests that never emitted a
            # MALFORMED_RESPONSE attempt (i.e. first-pass schema-valid output).
            gen_task = TaskType.PERSONA_GENERATION.value
            gen_rows = [r for r in rows if str(r.task) == gen_task or getattr(r.task, "value", None) == gen_task]
            if gen_rows:
                malformed = sum(
                    1
                    for r in gen_rows
                    if any(
                        (a or {}).get("failure_kind") == FailureKind.MALFORMED_RESPONSE.value
                        for a in (r.attempts or [])
                    )
                )
                schema_validity_rate = round(1 - malformed / len(gen_rows), 3)

            # Per-pool measured performance — only pools that actually served
            # requests appear; nothing is invented for empty pools.
            by_pool: dict[str, dict[str, Any]] = {}
            for r in rows:
                p = r.pool or "unpooled"
                st = by_pool.setdefault(
                    p, {"requests": 0, "success": 0, "latencies": [], "fallbacks": 0, "local": 0}
                )
                st["requests"] += 1
                if r.success:
                    st["success"] += 1
                if r.total_latency_ms is not None:
                    st["latencies"].append(r.total_latency_ms)
                if r.attempts and len(r.attempts) > 1:
                    st["fallbacks"] += 1
                if r.served_by_provider == OLLAMA:
                    st["local"] += 1
            pools = [
                {
                    "pool": name,
                    "requests": st["requests"],
                    "success_rate": round(st["success"] / st["requests"], 3),
                    "avg_latency_ms": (
                        round(sum(st["latencies"]) / len(st["latencies"]), 1)
                        if st["latencies"]
                        else None
                    ),
                    "fallback_rate": round(st["fallbacks"] / st["requests"], 3),
                    "local_serve_rate": round(st["local"] / st["requests"], 3),
                }
                for name, st in sorted(by_pool.items(), key=lambda kv: -kv[1]["requests"])
            ]

    return {
        "overall_health": {
            "total_personas_generated": total_personas,
            "schema_validity_rate": schema_validity_rate,
            "consistency_pass_rate": consistency_pass_rate,
            "avg_grounding_ratio": avg_grounding_ratio,
            "avg_latency_ms": avg_latency,
        },
        "pools": pools,
        "quality_gate": _load_latest_quality_gate(),
    }
