"""Qualitative interpretation and evidence synthesis for market segments.

Uses LLMService (TaskType.STRUCTURED_OUTPUT) to synthesize human-readable segment names,
grounded descriptions, and evidence citations from deterministic cluster distributions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.segmentation.clusterer import ClusterDistribution

logger = logging.getLogger(__name__)


class InterpretedSegment(BaseModel):
    name: str
    cluster_label: str
    description: str
    population_count: int
    population_percentage: float
    confidence_score: float
    status: str
    characteristics: dict[str, Any] = Field(default_factory=dict)
    variable_distributions: dict[str, Any] = Field(default_factory=dict)
    evidence_citations: list[dict[str, Any]] = Field(default_factory=list)
    differentiation_summary: str


def _match_evidence_to_cluster(
    cluster: ClusterDistribution,
    claims: list[Any],
) -> list[dict[str, Any]]:
    """Match relevant empirical research claims to this cluster."""
    matched = []
    cluster_traits_str = str(cluster.characteristics).lower()

    for c in claims:
        claim_text = getattr(c, "claim_text", "") or ""
        claim_cat = getattr(c, "category", "general") or "general"
        claim_status = getattr(c, "status", "supported") or "supported"
        claim_conf = getattr(c, "confidence", 0.8) or 0.8
        claim_id = getattr(c, "id", "")

        lower_claim = claim_text.lower()

        # Check relevance
        is_relevant = False
        if "budget" in cluster_traits_str and any(k in lower_claim for k in ("price", "cost", "budget", "bdt", "pay", "taka")):
            is_relevant = True
        elif "exam" in cluster_traits_str or "academic" in cluster_traits_str:
            if any(k in lower_claim for k in ("exam", "study", "plan", "time", "routine", "academic")):
                is_relevant = True
        elif any(w in lower_claim for w in ("student", "habit", "app", "mobile", "friction", "pain")):
            is_relevant = True

        if is_relevant:
            matched.append({
                "claim_id": claim_id,
                "claim_text": claim_text,
                "category": claim_cat,
                "status": claim_status,
                "confidence": claim_conf,
                "rationale": f"Grounds segment behavior in {claim_cat} evidence findings.",
            })
        if len(matched) >= 4:
            break

    return matched


def _deterministic_interpret_cluster(
    cluster: ClusterDistribution,
    study_context: dict[str, Any],
    claims: list[Any],
) -> InterpretedSegment:
    """Generate human-readable segment profile deterministically without LLM."""
    name_hint = cluster.characteristics.get("name_hint", "Target User Group")
    econ = cluster.characteristics.get("economics", {}).get("monthly_budget", {})
    budget_median = econ.get("median", 400) if isinstance(econ, dict) else 400
    currency = econ.get("currency", "BDT") if isinstance(econ, dict) else "BDT"

    # Build descriptive name
    if "price" in name_hint.lower() or "budget" in name_hint.lower() or budget_median <= 400:
        name = f"Budget-Conscious Students ({currency} {budget_median:.0f}/mo)"
        differentiation = "Differs by lower monthly spending tolerance and high prioritization of free/affordable core features."
        desc = (
            f"Represents {cluster.population_percentage}% of the empirical study population with a median budget of "
            f"{currency} {budget_median:.0f}. Highly sensitive to subscription pricing; seeks reliable tools that minimize recurring expenses."
        )
    elif "premium" in name_hint.lower() or "power" in name_hint.lower() or budget_median >= 1000:
        name = f"High-Engagement Power Users ({currency} {budget_median:.0f}/mo)"
        differentiation = "Differs by higher willingness to pay for comprehensive analytics, multi-device sync, and priority exam tools."
        desc = (
            f"Represents {cluster.population_percentage}% of respondents with strong readiness to invest in high-productivity software. "
            f"Shows heavy daily usage patterns and demand for advanced features."
        )
    else:
        name = f"Core Academic Planners ({currency} {budget_median:.0f}/mo)"
        differentiation = "Represents mainstream academic workflow users balancing structured scheduling with moderate software budgets."
        desc = (
            f"Represents {cluster.population_percentage}% of the target market. Focuses on structured daily study routines and "
            f"exam milestones with moderate price flexibility."
        )

    citations = _match_evidence_to_cluster(cluster, claims)

    return InterpretedSegment(
        name=name,
        cluster_label=cluster.cluster_label,
        description=desc,
        population_count=cluster.population_count,
        population_percentage=cluster.population_percentage,
        confidence_score=cluster.confidence_score,
        status=cluster.status,
        characteristics=cluster.characteristics,
        variable_distributions=cluster.variable_distributions,
        evidence_citations=citations,
        differentiation_summary=differentiation,
    )


async def interpret_market_segments(
    clusters: list[ClusterDistribution],
    study_context: dict[str, Any],
    claims: list[Any],
    llm_service: Optional[LLMService] = None,
) -> list[InterpretedSegment]:
    """Synthesize human-readable segment names and descriptions with LLM assistance or fallback."""
    if not llm_service:
        return [_deterministic_interpret_cluster(c, study_context, claims) for c in clusters]

    prompt_context = {
        "study_idea": study_context.get("prompt") or study_context.get("title", "Product Study"),
        "target_audience": study_context.get("target_audience", "Consumers"),
        "pricing_hypothesis": study_context.get("pricing_hypothesis", "Standard pricing"),
        "clusters": [
            {
                "label": c.cluster_label,
                "population_count": c.population_count,
                "population_percentage": c.population_percentage,
                "characteristics": c.characteristics,
                "traits": c.distinctive_traits,
            }
            for c in clusters
        ],
        "top_evidence_claims": [
            getattr(cl, "claim_text", "") for cl in claims[:6]
        ],
    }

    system_prompt = (
        "You are an expert market research analyst. Given deterministic population clusters and evidence claims, "
        "synthesize grounded, professional market segment profiles. For each cluster provide:\n"
        "1. name: Concise, descriptive segment name (e.g., 'Budget-Conscious Students', 'High-Intensity Exam Seekers'). "
        "Do NOT output generic labels like 'Cluster 0'.\n"
        "2. description: 2-3 sentence grounded description reflecting the cluster's actual budget, habits, and needs.\n"
        "3. differentiation_summary: 1 sentence explaining what makes this group meaningfully different.\n"
        "Output ONLY valid JSON matching: {\"segments\": [{\"cluster_label\": \"cluster_0\", \"name\": \"...\", \"description\": \"...\", \"differentiation_summary\": \"...\"}]}"
    )

    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=json.dumps(prompt_context)),
        ],
        json_mode=True,
        temperature=0.2,
    )

    try:
        result = await llm_service.complete(request)
        parsed = parse_llm_json(result.text)
        segments_data = parsed.get("segments", []) if isinstance(parsed, dict) else []

        interpreted: list[InterpretedSegment] = []
        for c in clusters:
            matching = next((s for s in segments_data if s.get("cluster_label") == c.cluster_label), None)
            if matching and matching.get("name") and matching.get("description"):
                citations = _match_evidence_to_cluster(c, claims)
                interpreted.append(
                    InterpretedSegment(
                        name=str(matching["name"]).strip(),
                        cluster_label=c.cluster_label,
                        description=str(matching["description"]).strip(),
                        population_count=c.population_count,
                        population_percentage=c.population_percentage,
                        confidence_score=c.confidence_score,
                        status=c.status,
                        characteristics=c.characteristics,
                        variable_distributions=c.variable_distributions,
                        evidence_citations=citations,
                        differentiation_summary=str(matching.get("differentiation_summary", "Distinct demographic and economic profile.")).strip(),
                    )
                )
            else:
                interpreted.append(_deterministic_interpret_cluster(c, study_context, claims))
        return interpreted
    except Exception:
        # Graceful fallback to deterministic generator — loudly, so canned
        # segment names are never mistaken for LLM synthesis in the logs.
        logger.warning(
            "LLM segment interpretation failed — using deterministic cluster labels",
            exc_info=True,
        )
        return [_deterministic_interpret_cluster(c, study_context, claims) for c in clusters]
