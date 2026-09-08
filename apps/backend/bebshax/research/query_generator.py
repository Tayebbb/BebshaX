"""Research query generation for study ideas.

The model writes 5–7 search queries for THIS idea/audience/pricing (Problem,
Competition, Pricing, Behaviour, Complaints). The result always says where it
came from: ``"llm"`` for model-written queries; ``"derived"`` only when no LLM
is wired, in which case the queries are transparent recombinations of the
study's own words (labelled, never presented as analysis). An unusable model
reply is retried once, then fails explicitly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from bebshax.llm.json_utils import parse_llm_json, unwrap_list
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.utils.explicit_failures import UnusableModelOutput

logger = logging.getLogger(__name__)

QUERY_GENERATION_FAILED = "query_generation_failed"
_MAX_ATTEMPTS = 2


@dataclass
class QuerySet:
    queries: list[str] = field(default_factory=list)
    source: str = "llm"  # "llm" | "derived"
    served_by: Optional[str] = None
    attempts: int = 0


def derive_queries_from_study_text(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
) -> list[str]:
    """Transparent recombination of the study's OWN words (no LLM, no analysis).
    Used only when no LLM service is wired and always labelled ``derived``."""
    clean_idea = re.sub(
        r"^(i'm building|we are building|i want to build|a platform for|an app for)\s+",
        "",
        idea.strip(),
        flags=re.IGNORECASE,
    )
    words = clean_idea.split()
    core_topic = " ".join(words[:6]) if len(words) > 6 else clean_idea
    audience = target_audience.strip() if target_audience else ""
    queries = [
        f"{audience} {core_topic} problems".strip(),
        f"{core_topic} alternatives",
        f"{core_topic} {audience} pricing".strip(),
        f"{core_topic} adoption behaviour",
    ]
    if pricing_hypothesis and pricing_hypothesis.strip():
        queries.append(f"{core_topic} {pricing_hypothesis.strip()}")
    return queries


async def generate_research_queries(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
    llm_service: Optional[LLMService] = None,
) -> QuerySet:
    """Queries for the evidence search, with their provenance."""
    if not idea or not idea.strip():
        raise ValueError("A business idea is required to generate research queries.")
    if not llm_service:
        return QuerySet(
            queries=derive_queries_from_study_text(idea, target_audience, pricing_hypothesis),
            source="derived",
        )

    system_prompt = (
        "You are an expert product researcher. Given a product idea, target audience, and pricing hypothesis, "
        "generate 5 to 7 specific, high-signal research search queries across 5 categories: "
        "Problem, Competition, Pricing, User Behavior, Complaints. Queries must name the concrete product "
        "category, market and audience from the brief — never generic phrases. "
        'Output ONLY a valid JSON object with one key "queries" holding an array of strings, '
        'e.g. {"queries": ["query 1", "query 2"]}. '
        + UNTRUSTED_RULE
    )
    brief = [f"PRODUCT IDEA: {idea}"]
    if target_audience:
        brief.append(f"TARGET AUDIENCE: {target_audience}")
    if pricing_hypothesis:
        brief.append(f"PRICING HYPOTHESIS: {pricing_hypothesis}")
    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=untrusted_block("RESEARCH_BRIEF", "\n".join(brief), source="study")),
        ],
        json_mode=True,
        temperature=0.2,
        max_output_tokens=300,
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
        items = unwrap_list(parsed, keys=("queries", "search_queries"))
        queries = [str(q).strip() for q in items if isinstance(q, (str, int, float)) and str(q).strip()]
        if len(queries) >= 3:
            return QuerySet(queries=queries[:8], source="llm", served_by=served_by, attempts=attempt)
        logger.warning("research-query reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)

    raise UnusableModelOutput(
        QUERY_GENERATION_FAILED,
        f"The model's research-query reply could not be used after {_MAX_ATTEMPTS} attempts.",
        attempts=_MAX_ATTEMPTS,
        served_by=served_by,
    )
