"""Comprehensive Research Report Generator Service (Rule R3).

Synthesizes stored study context, evidence sources, dataset signals, market segments,
synthetic personas, interview transcripts, extracted insights, and behavioral simulation runs
into a multi-section executive decision report with versioning and provenance tracking.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.behavioral.orm import (
    BehavioralTestResults,
    BehavioralTestRuns,
    BehavioralTests,
)
from bebshax.db.models import (
    DatasetSources,
    EvidenceClaims,
    EvidenceSources,
    MarketSegments,
    Personas,
    Studies,
    StudyReports,
    _utcnow,
)
from bebshax.interview.orm import Conversations, InterviewInsights
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_json_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.tenancy import ANONYMOUS_OWNER_ID
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput

logger = logging.getLogger(__name__)

REPORT_SYNTHESIS_FAILED = "report_synthesis_failed"
_MAX_ATTEMPTS = 2


REPORT_SYSTEM_PROMPT = """You are BebshaX Chief Research Intelligence Officer.
Synthesize the provided research study data into an authoritative, grounded 20-section market validation report.

CRITICAL RULES:
- Use ONLY the actual business idea, evidence, dataset signals, personas, interview answers, and behavioral simulation results provided in the prompt.
- NEVER invent unsupported claims or use generic platitudes.
- Clearly label synthetic persona simulations as exploratory simulation signals, and real research citations as empirical evidence.
- Return ONLY valid JSON (no markdown fences, no explanatory text outside the JSON object).
"""


class StudyReportService:
    """Orchestrates comprehensive study report generation, persistence, and versioning."""

    def __init__(self, session: AsyncSession, llm_service: Optional[LLMService] = None) -> None:
        self.session = session
        self.llm_service = llm_service

    async def generate_report(
        self,
        study_id: str,
        user_id: Optional[str] = None,
        custom_title: Optional[str] = None,
    ) -> StudyReports:
        """Generate and persist a new report version for the given study."""
        study = await self.session.get(Studies, study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")

        effective_user_id = user_id or study.user_id or ANONYMOUS_OWNER_ID

        # 1. Gather all study data from database
        evidence_sources = list(
            (
                await self.session.execute(
                    select(EvidenceSources).where(EvidenceSources.study_id == study_id)
                )
            ).scalars()
        )

        evidence_claims = list(
            (
                await self.session.execute(
                    select(EvidenceClaims).where(EvidenceClaims.study_id == study_id)
                )
            ).scalars()
        )

        datasets = list(
            (
                await self.session.execute(
                    select(DatasetSources).where(DatasetSources.study_id == study_id)
                )
            ).scalars()
        )

        segments = list(
            (
                await self.session.execute(
                    select(MarketSegments).where(MarketSegments.study_id == study_id)
                )
            ).scalars()
        )

        personas = list(
            (
                await self.session.execute(
                    select(Personas).where(Personas.study_id == study_id)
                )
            ).scalars()
        )

        conversations = list(
            (
                await self.session.execute(
                    select(Conversations).where(Conversations.study_id == study_id)
                )
            ).scalars()
        )

        interview_insights = list(
            (
                await self.session.execute(
                    select(InterviewInsights).where(InterviewInsights.study_id == study_id)
                )
            ).scalars()
        )

        behavioral_tests = list(
            (
                await self.session.execute(
                    select(BehavioralTests).where(BehavioralTests.study_id == study_id)
                )
            ).scalars()
        )

        behavioral_runs = list(
            (
                await self.session.execute(
                    select(BehavioralTestRuns).where(BehavioralTestRuns.study_id == study_id)
                )
            ).scalars()
        )

        behavioral_results = list(
            (
                await self.session.execute(
                    select(BehavioralTestResults).where(BehavioralTestResults.study_id == study_id)
                )
            ).scalars()
        )

        # 2. Determine version number
        latest_version_stmt = select(func.max(StudyReports.version)).where(
            StudyReports.study_id == study_id
        )
        max_ver = (await self.session.execute(latest_version_stmt)).scalar() or 0
        new_version = max_ver + 1

        # 3. Generate report data
        report_data = await self._synthesize_report_content(
            study=study,
            evidence_sources=evidence_sources,
            evidence_claims=evidence_claims,
            datasets=datasets,
            segments=segments,
            personas=personas,
            conversations=conversations,
            interview_insights=interview_insights,
            behavioral_tests=behavioral_tests,
            behavioral_runs=behavioral_runs,
            behavioral_results=behavioral_results,
            version=new_version,
            custom_title=custom_title,
        )

        # 4. Persist to StudyReports
        report_id = f"rep_{uuid.uuid4().hex[:16]}"
        report = StudyReports(
            id=report_id,
            study_id=study_id,
            user_id=effective_user_id,
            version=new_version,
            title=custom_title or report_data.get("title") or study.title or "Research Synthesis Report",
            executive_summary=report_data.get(
                "executive_summary",
                f"Validation report for {study.prompt or study.title}.",
            ),
            key_findings=report_data.get("key_findings", []),
            target_market_summary=report_data.get("target_market_summary"),
            market_context_summary=report_data.get("market_context_summary"),
            evidence_findings=report_data.get("evidence_findings", []),
            dataset_findings=report_data.get("dataset_findings", []),
            market_segments_summary=report_data.get("market_segments_summary", []),
            persona_overview=report_data.get("persona_overview", []),
            interview_findings=report_data.get("interview_findings", []),
            major_pain_points=report_data.get("major_pain_points", []),
            customer_needs=report_data.get("customer_needs", []),
            behavioral_results=report_data.get("behavioral_results", []),
            pricing_signals=report_data.get("pricing_signals", []),
            major_risks=report_data.get("major_risks", []),
            opportunities=report_data.get("opportunities", []),
            strongest_segments=report_data.get("strongest_segments", []),
            recommendations=report_data.get("recommendations", []),
            validation_summary=report_data.get("validation_summary"),
            limitations=report_data.get("limitations"),
            metrics=report_data.get(
                "metrics",
                {
                    "total_interviews": len(conversations),
                    "total_personas": len(personas),
                    "total_claims": len(evidence_claims),
                    # Honest absence: scores are only present when the LLM
                    # synthesis computed them from the actual study data.
                    "confidence_score": None,
                    "demand_score": None,
                },
            ),
            is_synthetic=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )

        self.session.add(report)

        # Update Study findings & status
        study.findings = {
            "report_id": report_id,
            "version": new_version,
            "title": report.title,
            "executive_summary": report.executive_summary,
            "key_findings": report.key_findings,
            "metrics": report.metrics,
            "generated_at": _utcnow().isoformat(),
        }
        study.status = "completed"
        study.step = 5
        study.updated_at = _utcnow()

        await self.session.commit()
        await self.session.refresh(report)
        return report

    async def _synthesize_report_content(
        self,
        study: Studies,
        evidence_sources: list[EvidenceSources],
        evidence_claims: list[EvidenceClaims],
        datasets: list[DatasetSources],
        segments: list[MarketSegments],
        personas: list[Personas],
        conversations: list[Conversations],
        interview_insights: list[InterviewInsights],
        behavioral_tests: list[BehavioralTests],
        behavioral_runs: list[BehavioralTestRuns],
        behavioral_results: list[BehavioralTestResults],
        version: int,
        custom_title: Optional[str] = None,
    ) -> dict[str, Any]:
        """Synthesize the report with the model from the stored study data.
        Raises ``LLMUnavailable`` (no service), ``UnusableModelOutput`` (after one
        retry) or any ``LLMError`` — there is no template report."""
        prompt_text = study.prompt or study.title or "Business Research Study"
        target_aud = study.target_audience or ""
        pricing_hyp = study.pricing_hypothesis or ""

        # Build context snapshot
        study_context = {
            "business_idea": prompt_text,
            "target_audience": target_aud,
            "pricing_hypothesis": pricing_hyp,
            "research_goal": study.goal,
            "evidence_claims_count": len(evidence_claims),
            "evidence_claims_sample": [
                {"claim": c.claim_text, "category": c.category, "confidence": c.confidence}
                for c in evidence_claims[:8]
            ],
            "dataset_count": len(datasets),
            "datasets_sample": [
                {"name": d.name, "rows": d.row_count, "segments": len(d.segments or [])}
                for d in datasets[:3]
            ],
            "market_segments": [
                {"name": s.name, "share": s.population_percentage, "description": s.description}
                for s in segments[:5]
            ],
            "personas_count": len(personas),
            "personas_sample": [
                {
                    "name": p.name,
                    "archetype": p.archetype,
                    "occupation": (p.demographics or {}).get("occupation", "User"),
                    "grounding_score": p.grounding_score,
                    "goals": (p.goals or [])[:2],
                    "pain_points": (p.pain_points or [])[:2],
                }
                for p in personas[:6]
            ],
            "completed_interviews": len(conversations),
            "interview_insights_sample": [
                {
                    "title": i.title,
                    "type": i.type,
                    "description": i.description,
                    "turns": i.supporting_turn_numbers,
                }
                for i in interview_insights[:8]
            ],
            "behavioral_simulations": [
                {
                    "test_type": t.test_type,
                    "scenario": t.name,
                    "run_count": len(t.scenarios or []),
                }
                for t in behavioral_tests[:4]
            ],
            "behavioral_results_sample": [
                {
                    "persona": r.persona_name,
                    "decision": r.decision_label,
                    "probability": r.probability,
                    "key_factors": r.key_factors,
                }
                for r in behavioral_results[:6]
            ],
        }

        if self.llm_service is None:
            raise LLMUnavailable("Report synthesis")

        # Stored study data is DATA for the model (persona quotes, interview
        # answers and scraped evidence may contain instructions).
        context_block = untrusted_json_block("STUDY_CONTEXT", study_context, source="study records")
        title_hint = json.dumps(custom_title or study.title or "Research Synthesis Report", ensure_ascii=False)
        user_msg = (
            "Synthesize this research study into a complete 20-section JSON report.\n\n"
            f"{context_block}\n\n"
            "Output Format:\n"
            "{\n"
            f'  "title": {title_hint},\n'
            '  "executive_summary": "Crisp 2-3 paragraph executive summary grounded in findings",\n'
            '  "key_findings": ["Finding 1 with concrete data", "Finding 2", "Finding 3"],\n'
            '  "target_market_summary": "Detailed target market overview",\n'
            '  "market_context_summary": "Market macro and competitive context",\n'
            '  "evidence_findings": [{"title": "...", "claim": "...", "confidence": 0.9, "source": "..."}],\n'
            '  "dataset_findings": [{"name": "...", "insight": "...", "variables": ["..."]}],\n'
            '  "market_segments_summary": [{"name": "...", "percentage": 35.0, "description": "..."}],\n'
            '  "persona_overview": [{"name": "...", "archetype": "...", "segment": "...", "key_takeaway": "..."}],\n'
            '  "interview_findings": [{"topic": "...", "finding": "...", "supporting_personas": ["..."], "turn_citations": ["Turn 2", "Turn 4"]}],\n'
            '  "major_pain_points": [{"pain_point": "...", "severity": "High", "frequency": "Frequent"}],\n'
            '  "customer_needs": [{"need": "...", "priority": "Crucial", "context": "..."}],\n'
            '  "behavioral_results": [{"test_type": "...", "scenario": "...", "decision": "...", "average_likelihood": 0.78, "key_objection": "...", "key_motivator": "..."}],\n'
            '  "pricing_signals": [{"price_point": "...", "sentiment": "...", "acceptable_range": "..."}],\n'
            '  "major_risks": ["Risk 1", "Risk 2"],\n'
            '  "opportunities": ["Opportunity 1", "Opportunity 2"],\n'
            '  "strongest_segments": ["Segment A", "Segment B"],\n'
            '  "recommendations": ["Recommendation 1", "Recommendation 2", "Recommendation 3"],\n'
            '  "validation_summary": "Synthesis of validation score and product-market fit signal",\n'
            '  "limitations": "Clear disclosure of synthetic simulation boundaries and dataset coverage",\n'
            f'  "metrics": {{"total_interviews": {len(conversations)}, "total_personas": {len(personas)}, "total_claims": {len(evidence_claims)}, '
            '"confidence_score": <float 0.0-1.0: YOUR assessment of evidence coverage — lower it when interviews are few or claims are thin>, '
            '"demand_score": <integer 0-100: YOUR assessment of demand strength derived ONLY from the interview answers and pricing signals above>}\n'
            "}\n"
            "Sections with no underlying data in STUDY_CONTEXT must be empty lists or state the absence plainly — never filled with generic statements."
        )

        llm_req = LLMRequest(
            task=TaskType.REPORT_GENERATION,
            messages=[
                ChatMessage(role="system", content=REPORT_SYSTEM_PROMPT + UNTRUSTED_RULE),
                ChatMessage(role="user", content=user_msg),
            ],
            json_mode=True,
            temperature=0.4,
            # The 20-section report JSON does not fit provider default output
            # caps (~1024 tokens); without this the JSON is silently truncated.
            max_output_tokens=8000,
        )
        served_by = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if attempt > 1:
                llm_req = llm_req.retry_copy()
            result = await self.llm_service.complete(llm_req)  # LLMError propagates
            served_by = f"{result.provider}/{result.model}"
            try:
                parsed = parse_llm_json(result.text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict) and str(parsed.get("executive_summary") or "").strip():
                metrics = parsed.get("metrics")
                if not isinstance(metrics, dict):
                    metrics = {}
                metrics.update(
                    {
                        "total_interviews": len(conversations),
                        "total_personas": len(personas),
                        "total_claims": len(evidence_claims),
                        "synthesis_source": "llm",
                        "served_by": served_by,
                        "llm_request_id": llm_req.request_id,
                        "attempts": attempt,
                    }
                )
                parsed["metrics"] = metrics
                return parsed
            logger.warning("report synthesis reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)

        raise UnusableModelOutput(
            REPORT_SYNTHESIS_FAILED,
            f"The model's report reply could not be used after {_MAX_ATTEMPTS} attempts; no template report was written.",
            attempts=_MAX_ATTEMPTS,
            served_by=served_by,
        )
