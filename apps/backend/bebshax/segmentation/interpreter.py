"""Qualitative interpretation and evidence synthesis for market segments.

Uses LLMService (TaskType.STRUCTURED_OUTPUT) to write segment names, grounded
descriptions and differentiation from the OBSERVED cluster distributions.
Evidence citations are matched lexically to what the cluster actually shows.
There are no template names: no LLM or an unusable reply fails explicitly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_json_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.research.search_provider import lexical_relevance
from bebshax.segmentation.clusterer import ClusterDistribution
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput

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


SEGMENT_INTERPRETATION_FAILED = "segment_interpretation_failed"
_MAX_ATTEMPTS = 2
_MAX_CITATIONS = 4
_MIN_CLAIM_RELEVANCE = 0.12


def _cluster_text(cluster: ClusterDistribution) -> str:
    """Words that actually describe this cluster: partition variable, observed
    variable names, top categories and traits — no domain vocabulary."""
    parts: list[str] = [cluster.characteristics.get("name_hint", "") or "", *cluster.distinctive_traits]
    parts.append(str(cluster.characteristics.get("partition_variable", "")))
    observed = cluster.characteristics.get("observed") or cluster.variable_distributions or {}
    for name, dist in observed.items():
        parts.append(str(name).replace("_", " "))
        if isinstance(dist, dict):
            for cat in dist.get("top_categories", [])[:3]:
                parts.append(str(cat.get("category", "")))
    constraints = cluster.characteristics.get("observed_constraints") or {}
    parts.extend(f"{k} {v}" for k, v in constraints.items() if not isinstance(v, (dict, list)))
    return " ".join(p for p in parts if p)


def _match_evidence_to_cluster(
    cluster: ClusterDistribution,
    claims: list[Any],
) -> list[dict[str, Any]]:
    """Claims lexically related to what was OBSERVED in this cluster. Nothing
    matches when nothing is related — no padding."""
    cluster_text = _cluster_text(cluster)
    scored: list[tuple[float, dict[str, Any]]] = []
    for c in claims:
        claim_text = getattr(c, "claim_text", "") or ""
        if not claim_text:
            continue
        # Share of the claim's own words that appear in the cluster's observed vocabulary.
        relevance = lexical_relevance(claim_text, cluster_text)
        if relevance < _MIN_CLAIM_RELEVANCE:
            continue
        category = getattr(c, "category", "general") or "general"
        scored.append(
            (
                relevance,
                {
                    "claim_id": getattr(c, "id", ""),
                    "claim_text": claim_text,
                    "category": category,
                    "status": getattr(c, "status", "inference") or "inference",
                    "confidence": getattr(c, "confidence", 0.0) or 0.0,
                    "relevance": round(relevance, 3),
                    "rationale": f"Shares vocabulary with this cluster's observed {category} traits.",
                },
            )
        )
    scored.sort(key=lambda t: -t[0])
    return [m for _, m in scored[:_MAX_CITATIONS]]


async def interpret_market_segments(
    clusters: list[ClusterDistribution],
    study_context: dict[str, Any],
    claims: list[Any],
    llm_service: Optional[LLMService] = None,
) -> list[InterpretedSegment]:
    """Names and descriptions written by the model FROM the observed cluster
    statistics. Raises ``LLMUnavailable`` (no service), ``UnusableModelOutput``
    (reply unusable for at least one cluster after a retry) or any ``LLMError``
    — there are no canned segment labels."""
    if not clusters:
        return []
    if not llm_service:
        raise LLMUnavailable("Segment interpretation")

    prompt_context = {
        "study_idea": study_context.get("prompt") or study_context.get("title", ""),
        "target_audience": study_context.get("target_audience") or "",
        "pricing_hypothesis": study_context.get("pricing_hypothesis") or "",
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
        "top_evidence_claims": [getattr(cl, "claim_text", "") for cl in claims[:6]],
    }

    system_prompt = (
        "You are an expert market research analyst. You receive population clusters computed from a study's "
        "dataset (quantile bands or categorical groups with observed distributions) plus evidence claims. "
        "For EACH cluster provide:\n"
        "1. name: a concise, descriptive segment name derived from the observed variables and the study's own "
        "audience/market (never a generic label like 'Cluster 0', never a name that the data does not support).\n"
        "2. description: 2-3 sentences that cite the cluster's actual numbers (ranges, medians, category shares).\n"
        "3. differentiation_summary: 1 sentence on what measurably separates this group from the others.\n"
        'Output ONLY valid JSON matching: {"segments": [{"cluster_label": "cluster_0", "name": "...", '
        '"description": "...", "differentiation_summary": "..."}]} with one entry per cluster label.\n'
        + UNTRUSTED_RULE
    )

    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(
                role="user",
                content=untrusted_json_block("CLUSTER_ANALYSIS", prompt_context, source="dataset statistics + evidence"),
            ),
        ],
        json_mode=True,
        temperature=0.2,
        max_output_tokens=1200,
    )

    served_by = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            request = request.retry_copy()
        result = await llm_service.complete(request)  # LLMError propagates
        served_by = f"{result.provider}/{result.model}"
        try:
            parsed = parse_llm_json(result.text)
        except ValueError:
            parsed = None
        segments_data = parsed.get("segments", []) if isinstance(parsed, dict) else parsed
        if not isinstance(segments_data, list):
            logger.warning("segment interpretation reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue

        by_label = {
            str(s.get("cluster_label")): s
            for s in segments_data
            if isinstance(s, dict) and str(s.get("name") or "").strip() and str(s.get("description") or "").strip()
        }
        missing = [c.cluster_label for c in clusters if c.cluster_label not in by_label]
        if missing:
            logger.warning("segment interpretation missed %s (attempt %d/%d)", missing, attempt, _MAX_ATTEMPTS)
            continue

        interpreted: list[InterpretedSegment] = []
        for c in clusters:
            matching = by_label[c.cluster_label]
            interpreted.append(
                InterpretedSegment(
                    name=str(matching["name"]).strip(),
                    cluster_label=c.cluster_label,
                    description=str(matching["description"]).strip(),
                    population_count=c.population_count,
                    population_percentage=c.population_percentage,
                    confidence_score=c.confidence_score,
                    status=c.status,
                    characteristics={**c.characteristics, "interpretation_source": "llm", "served_by": served_by},
                    variable_distributions=c.variable_distributions,
                    evidence_citations=_match_evidence_to_cluster(c, claims),
                    differentiation_summary=str(matching.get("differentiation_summary") or "").strip(),
                )
            )
        return interpreted

    raise UnusableModelOutput(
        SEGMENT_INTERPRETATION_FAILED,
        f"The model's segment-interpretation reply could not be used after {_MAX_ATTEMPTS} attempts; "
        "no canned segment names were substituted.",
        attempts=_MAX_ATTEMPTS,
        served_by=served_by,
    )
