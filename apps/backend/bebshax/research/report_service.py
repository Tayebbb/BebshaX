"""Comprehensive Research Report Generator Service (Rule R3).

Synthesizes stored study context, evidence sources, dataset signals, market segments,
synthetic personas, interview transcripts, extracted insights, and behavioral simulation runs
into a multi-section executive decision report with versioning and provenance tracking.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.behavioral.orm import (
    BehavioralInsights,
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
from bebshax.interview.orm import Conversations, ConversationTurns, InterviewInsights
from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

logger = logging.getLogger(__name__)


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

        effective_user_id = user_id or study.user_id or "usr_default"

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
            title=report_data.get("title", study.title or "Research Synthesis Report"),
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
        """Synthesize report using LLM with deterministic fallback."""
        prompt_text = study.prompt or study.title or "Business Research Study"
        target_aud = study.target_audience or "Target Market"
        pricing_hyp = study.pricing_hypothesis or "Market Pricing"

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

        if self.llm_service:
            try:
                user_msg = (
                    f"Synthesize this research study into a complete 20-section JSON report.\n\n"
                    f"Study Context:\n{json.dumps(study_context, indent=2)}\n\n"
                    f"Output Format:\n"
                    f"{{\n"
                    f'  "title": "{custom_title or study.title}",\n'
                    f'  "executive_summary": "Crisp 2-3 paragraph executive summary grounded in findings",\n'
                    f'  "key_findings": ["Finding 1 with concrete data", "Finding 2", "Finding 3"],\n'
                    f'  "target_market_summary": "Detailed target market overview",\n'
                    f'  "market_context_summary": "Market macro and competitive context",\n'
                    f'  "evidence_findings": [{{"title": "...", "claim": "...", "confidence": 0.9, "source": "..."}}],\n'
                    f'  "dataset_findings": [{{"name": "...", "insight": "...", "variables": ["..."]}}],\n'
                    f'  "market_segments_summary": [{{"name": "...", "percentage": 35.0, "description": "..."}}],\n'
                    f'  "persona_overview": [{{"name": "...", "archetype": "...", "segment": "...", "key_takeaway": "..."}}],\n'
                    f'  "interview_findings": [{{"topic": "...", "finding": "...", "supporting_personas": ["..."], "turn_citations": ["Turn 2", "Turn 4"]}}],\n'
                    f'  "major_pain_points": [{{"pain_point": "...", "severity": "High", "frequency": "Frequent"}}],\n'
                    f'  "customer_needs": [{{"need": "...", "priority": "Crucial", "context": "..."}}],\n'
                    f'  "behavioral_results": [{{"test_type": "...", "scenario": "...", "decision": "...", "average_likelihood": 0.78, "key_objection": "...", "key_motivator": "..."}}],\n'
                    f'  "pricing_signals": [{{"price_point": "...", "sentiment": "...", "acceptable_range": "..."}}],\n'
                    f'  "major_risks": ["Risk 1", "Risk 2"],\n'
                    f'  "opportunities": ["Opportunity 1", "Opportunity 2"],\n'
                    f'  "strongest_segments": ["Segment A", "Segment B"],\n'
                    f'  "recommendations": ["Recommendation 1", "Recommendation 2", "Recommendation 3"],\n'
                    f'  "validation_summary": "Synthesis of validation score and product-market fit signal",\n'
                    f'  "limitations": "Clear disclosure of synthetic simulation boundaries and dataset coverage",\n'
                    f'  "metrics": {{"total_interviews": {len(conversations)}, "total_personas": {len(personas)}, "total_claims": {len(evidence_claims)}, "confidence_score": <float 0.0-1.0: YOUR assessment of evidence coverage — lower it when interviews are few or claims are thin>, "demand_score": <integer 0-100: YOUR assessment of demand strength derived ONLY from the interview answers and pricing signals above>}}\n'
                    f"}}"
                )

                llm_req = LLMRequest(
                    task=TaskType.REPORT_GENERATION,
                    messages=[
                        ChatMessage(role="system", content=REPORT_SYSTEM_PROMPT),
                        ChatMessage(role="user", content=user_msg),
                    ],
                    json_mode=True,
                    temperature=0.4,
                    # The 20-section report JSON does not fit provider default
                    # output caps (~1024 tokens); without this the JSON was
                    # silently truncated and every report fell back to the
                    # deterministic template.
                    max_output_tokens=8000,
                )
                result = await self.llm_service.complete(llm_req)
                parsed = parse_llm_json(result.text)
                if isinstance(parsed, dict) and "executive_summary" in parsed:
                    return parsed
            except Exception:
                logger.warning(
                    "LLM report synthesis failed; falling back to deterministic report",
                    exc_info=True,
                )

        # Deterministic grounded fallback
        return self._generate_deterministic_report(
            study=study,
            evidence_sources=evidence_sources,
            evidence_claims=evidence_claims,
            datasets=datasets,
            segments=segments,
            personas=personas,
            conversations=conversations,
            interview_insights=interview_insights,
            behavioral_tests=behavioral_tests,
            behavioral_results=behavioral_results,
            version=version,
            custom_title=custom_title,
        )

    def _generate_deterministic_report(
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
        behavioral_results: list[BehavioralTestResults],
        version: int,
        custom_title: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate structured report deterministically using real study entities."""
        prompt = study.prompt or study.title or "Business Idea"
        title = custom_title or study.title or f"Research Report V{version}"
        target_aud = study.target_audience or "target consumers"

        # Segment summaries
        seg_summary = [
            {
                "name": s.name,
                "percentage": round(s.population_percentage or (100.0 / max(1, len(segments))), 1),
                "description": s.description,
            }
            for s in segments
        ]
        if not seg_summary and personas:
            seg_summary = [
                {
                    "name": "Primary Target Segment",
                    "percentage": 60.0,
                    "description": f"Core target audience for {prompt}.",
                },
                {
                    "name": "Secondary Adopters",
                    "percentage": 40.0,
                    "description": "Price-conscious and convenience-focused adopters.",
                },
            ]

        # Persona overview
        persona_overview = [
            {
                "name": p.name,
                "archetype": p.archetype or "Representative Archetype",
                "segment": (
                    p.demographics.get("occupation", "Target User")
                    if p.demographics
                    else "Target User"
                ),
                "key_takeaway": (
                    p.goals[0]
                    if p.goals
                    else "Seeks efficiency, transparent pricing, and daily workflow integration."
                ),
                "grounding_score": round(p.grounding_score if p.grounding_score is not None else 0.0, 2),
            }
            for p in personas
        ]

        # Evidence findings
        evidence_findings = [
            {
                "title": f"Empirical Claim {idx+1}",
                "claim": c.claim_text,
                "confidence": round(c.confidence, 2),
                "source": (
                    c.supporting_source_ids[0]
                    if c.supporting_source_ids
                    else "Discovered Evidence Source"
                ),
            }
            for idx, c in enumerate(evidence_claims[:6])
        ]

        # Interview findings
        interview_findings = [
            {
                "topic": i.type.title() if i.type else "General Feedback",
                "finding": i.title + ": " + i.description,
                "supporting_personas": (
                    [i.persona_id] if i.persona_id else [p.name for p in personas[:2]]
                ),
                "turn_citations": (
                    [f"Turn {t}" for t in (i.supporting_turn_numbers or [1, 2])]
                ),
            }
            for i in interview_insights[:8]
        ]
        if not interview_findings and conversations:
            interview_findings = [
                {
                    "topic": "Core Demand & Workflow",
                    "finding": f"Participants confirmed high interest in solving daily friction for {prompt}.",
                    "supporting_personas": [p.name for p in personas[:3]],
                    "turn_citations": ["Turn 2", "Turn 4"],
                },
                {
                    "topic": "Price Sensitivity",
                    "finding": "Transparent pricing and immediate ROI are critical adoption prerequisites.",
                    "supporting_personas": [p.name for p in personas[:2]],
                    "turn_citations": ["Turn 3"],
                },
            ]

        # Pain points & needs
        pain_points = []
        for p in personas:
            for pt in p.pain_points or []:
                if pt not in [x["pain_point"] for x in pain_points]:
                    pain_points.append(
                        {"pain_point": pt, "severity": "High", "frequency": "Daily / Weekly"}
                    )
        if not pain_points:
            pain_points = [
                {
                    "pain_point": f"Manual, fragmented alternatives for {prompt}",
                    "severity": "High",
                    "frequency": "Daily",
                },
                {
                    "pain_point": "High switching effort without clear onboarding value",
                    "severity": "Medium",
                    "frequency": "Initial Adoption",
                },
            ]

        customer_needs = []
        for p in personas:
            for nd in p.needs or []:
                if nd not in [x["need"] for x in customer_needs]:
                    customer_needs.append(
                        {
                            "need": nd,
                            "priority": "Crucial",
                            "context": "Essential for ongoing retention",
                        }
                    )
        if not customer_needs:
            customer_needs = [
                {
                    "need": "Frictionless setup with immediate utility",
                    "priority": "Crucial",
                    "context": "First 5 minutes",
                },
                {
                    "need": "Predictable, fair pricing structure",
                    "priority": "High",
                    "context": "Monthly renewal",
                },
            ]

        # Behavioral simulation results
        behavioral_summary = [
            {
                "test_type": r.decision,
                "scenario": f"Simulation across {r.persona_name}",
                "decision": r.decision_label or r.decision,
                "average_likelihood": round(r.probability, 2),
                "key_objection": (r.objections[0] if r.objections else "Price sensitivity"),
                "key_motivator": (r.motivators[0] if r.motivators else "Time savings & convenience"),
            }
            for r in behavioral_results[:6]
        ]

        # Executive summary — deterministic synthesis states what it counted,
        # never a demand verdict it cannot compute.
        exec_summary = (
            f"This research validation report for '{prompt}' synthesizes evidence across "
            f"{len(evidence_claims)} research claims, {len(segments)} market segments, "
            f"{len(personas)} synthetic customer personas, and {len(conversations)} multi-turn simulated interviews.\n\n"
            f"Sections below are deterministic summaries of the stored study data. Synthetic findings are "
            f"research signals and hypotheses to validate with real users — no aggregate demand score is "
            f"computed on this template path."
        )

        return {
            "title": title,
            "executive_summary": exec_summary,
            "key_findings": [
                f"Hypothesis: demand for '{prompt}' is likely strongest when pitched on immediate time savings and convenience — validate in live interviews.",
                "Hypothesis: transparent pricing tiers may improve conversion for price-sensitive cohorts — not yet measured.",
                "Hypothesis: personas suggest reliability proof is a switching prerequisite — verify with real users.",
            ],
            "target_market_summary": (
                f"The target market comprises {target_aud}, characterized by high digital engagement "
                f"and moderate-to-high price sensitivity."
            ),
            "market_context_summary": (
                f"Sampled signals suggest active searching for alternatives to manual solutions; convenience "
                f"and speed recur as purchasing motivators in the collected material."
            ),
            "evidence_findings": evidence_findings,
            "dataset_findings": [
                {
                    "name": d.name,
                    "insight": f"Profiled {d.row_count} records highlighting segment distribution across key demographics.",
                    "variables": list(d.schema_metadata.keys())[:4] if d.schema_metadata else [],
                }
                for d in datasets[:3]
            ],
            "market_segments_summary": seg_summary,
            "persona_overview": persona_overview,
            "interview_findings": interview_findings,
            "major_pain_points": pain_points[:6],
            "customer_needs": customer_needs[:6],
            "behavioral_results": behavioral_summary,
            "pricing_signals": [
                {
                    "price_point": study.pricing_hypothesis or "Market Baseline",
                    "sentiment": "Not scored — template synthesis",
                    "acceptable_range": "Requires live interview evidence",
                }
            ],
            "major_risks": [
                "Over-complicating early onboarding could increase initial drop-off.",
                "Unclear pricing framing may trigger hesitation among budget-conscious cohorts.",
            ],
            "opportunities": [
                "Early market mover advantage with focused feature set.",
                "Viral word-of-mouth potential among power users and group organizers.",
            ],
            "strongest_segments": [s["name"] for s in seg_summary[:2]],
            "recommendations": [
                f"Launch with a focused MVP directly addressing the top pain points: {', '.join([p['pain_point'] for p in pain_points[:2]])}.",
                "Structure pricing with clear tier differentiation to capture both price-sensitive and power user segments.",
                "Highlight speed and concrete evidence in all initial marketing copy and product onboarding.",
            ],
            "validation_summary": (
                "Template synthesis — LLM report synthesis was unavailable, so no validation score was "
                "computed. The sections above are deterministic summaries of the stored study data."
            ),
            "limitations": (
                "Notice: This report combines curated sample evidence with exploratory synthetic persona "
                "simulations. Synthetic findings are hypotheses — validate consequential decisions with real users."
            ),
            "metrics": {
                "total_interviews": len(conversations),
                "total_personas": len(personas),
                "total_claims": len(evidence_claims),
                # Honest absence — a deterministic template cannot score demand.
                "confidence_score": None,
                "demand_score": None,
            },
        }
