"""Structured Research Planning Engine for BebshaX.

Analyzes the user's business idea and produces a comprehensive, structured research plan:
- Target Market definition
- Problem Areas & user frictions
- Behavioral research questions
- Economic & Willingness-to-Pay questions
- Competition & Alternative solution questions
- Market size & Macro demographic questions
- High-signal Dataset Requirements (categories, target variables, geographic & population scopes)

Supports LLM-assisted generation via LLMService (TaskType.STRUCTURED_OUTPUT).
There is no template plan: without an LLM, or when the model's reply is
unusable after one retry, the run step fails explicitly (RULES.md R2).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from pydantic import BaseModel, Field

from bebshax.llm.json_utils import parse_llm_json
from bebshax.llm.prompt_safety import UNTRUSTED_RULE, untrusted_block
from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType
from bebshax.utils.explicit_failures import LLMUnavailable, UnusableModelOutput

logger = logging.getLogger(__name__)

RESEARCH_PLAN_FAILED = "research_plan_failed"
_MAX_ATTEMPTS = 2


class DatasetRequirementSpec(BaseModel):
    category: str = Field(..., description="High-level dataset domain (e.g., customer_spending, usage_behaviour, sme_operations)")
    description: str = Field(..., description="Why this dataset category is critical to validating the business idea")
    target_variables: list[str] = Field(default_factory=list, description="Specific variables/columns needed for segmentation and profiling")
    # Derived from the study's target market by the model — never a regional default.
    geographic_scope: str = Field(default="", description="Geographic scope of the target market")
    population_scope: str = Field(default="", description="Specific population subset")


class ResearchPlanResult(BaseModel):
    business_idea: str
    target_market: list[str]
    problem_areas: list[str]
    behavioral_questions: list[str]
    economic_questions: list[str]
    competition_questions: list[str]
    market_questions: list[str]
    dataset_requirements: list[DatasetRequirementSpec]
    summary: str
    # ISO-3166 alpha-3 codes of the countries the target market lives in, as
    # inferred by the model from the brief. Empty when the brief names none —
    # country-bound data sources then stay silent instead of assuming one.
    target_countries: list[str] = Field(default_factory=list)
    source: str = "llm"  # always model-written; kept for consumers that read it
    served_by: Optional[str] = None
    llm_request_id: Optional[str] = None
    fallback_reason: Optional[str] = None  # only ever "retried_after_unparseable_reply"


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


_ISO3 = re.compile(r"^[A-Z]{3}$")


def _iso3_list(value) -> list[str]:
    codes = [c.upper() for c in _str_list(value)]
    return list(dict.fromkeys(c for c in codes if _ISO3.match(c)))[:5]


async def generate_structured_research_plan(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
    llm_service: Optional[LLMService] = None,
) -> ResearchPlanResult:
    """A research plan written by the model for THIS idea. Raises ``LLMUnavailable``
    when no service is wired, ``UnusableModelOutput`` after one retry, or any
    ``LLMError`` — never a template."""
    if not llm_service:
        raise LLMUnavailable("Research planning")

    # Researcher text is DATA: wrapped so it cannot restate the instructions, and
    # JSON-encoded inside the schema template so quotes cannot break out of the
    # "business_idea" string.
    context_lines = [f"BUSINESS IDEA: {idea}"]
    if target_audience:
        context_lines.append(f"TARGET AUDIENCE: {target_audience}")
    if pricing_hypothesis:
        context_lines.append(f"PRICING HYPOTHESIS: {pricing_hypothesis}")
    context_block = untrusted_block("RESEARCH_BRIEF", "\n".join(context_lines), source="study")

    prompt = f"""You are the Chief Research Officer for BebshaX, an empirical customer validation platform.
Analyze the following business idea and generate a comprehensive, structured research plan to discover evidence and public datasets.
Every item must be specific to this idea, its stated audience and its market/region as described in the brief — infer the geography from the brief, never assume one.
{UNTRUSTED_RULE}

{context_block}

Produce a valid JSON object matching this exact schema:
{{
  "business_idea": {json.dumps(idea, ensure_ascii=False)},
  "target_market": ["segment 1", "segment 2", "segment 3"],
  "problem_areas": ["problem 1", "problem 2", "problem 3", "problem 4"],
  "behavioral_questions": ["question 1", "question 2", "question 3"],
  "economic_questions": ["question 1 regarding willingness to pay and budget", "question 2", "question 3"],
  "competition_questions": ["question 1 on alternatives", "question 2"],
  "market_questions": ["question 1 on market size and demographics", "question 2"],
  "dataset_requirements": [
    {{
      "category": "dataset_category_name",
      "description": "Why this dataset is essential",
      "target_variables": ["variable_1", "variable_2", "variable_3"],
      "geographic_scope": "the geographic scope of the target market described in the brief",
      "population_scope": "Specific population group"
    }}
  ],
  "summary": "Concise 1-2 sentence overview of the research scope",
  "target_countries": ["ISO-3166 alpha-3 code(s) of the countries the target market lives in, inferred from the brief; [] if the brief gives no geographic clue"]
}}

Respond ONLY with valid JSON."""

    req = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[ChatMessage(role="user", content=prompt)],
        json_mode=True,
        temperature=0.3,
        max_output_tokens=1500,
    )
    served_by = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if attempt > 1:
            req = req.retry_copy()
        res = await llm_service.complete(req)  # LLMError propagates
        served_by = f"{res.provider}/{res.model}"
        try:
            data = parse_llm_json(res.text)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            logger.warning("research plan reply unusable (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue
        reqs = [
            DatasetRequirementSpec(
                category=str(r.get("category") or "").strip() or "general",
                description=str(r.get("description") or "").strip(),
                target_variables=_str_list(r.get("target_variables")),
                geographic_scope=str(r.get("geographic_scope") or "").strip(),
                population_scope=str(r.get("population_scope") or "").strip(),
            )
            for r in (data.get("dataset_requirements") or [])
            if isinstance(r, dict)
        ]
        target_market = _str_list(data.get("target_market"))
        problem_areas = _str_list(data.get("problem_areas"))
        if not (target_market and problem_areas and reqs):
            logger.warning("research plan reply incomplete (attempt %d/%d)", attempt, _MAX_ATTEMPTS)
            continue
        return ResearchPlanResult(
            business_idea=idea,
            target_market=target_market,
            problem_areas=problem_areas,
            behavioral_questions=_str_list(data.get("behavioral_questions")),
            economic_questions=_str_list(data.get("economic_questions")),
            competition_questions=_str_list(data.get("competition_questions")),
            market_questions=_str_list(data.get("market_questions")),
            dataset_requirements=reqs,
            summary=str(data.get("summary") or "").strip() or f"Research plan for {idea}",
            target_countries=_iso3_list(data.get("target_countries")),
            source="llm",
            served_by=served_by,
            llm_request_id=req.request_id,
            fallback_reason="retried_after_unparseable_reply" if attempt > 1 else None,
        )
    raise UnusableModelOutput(
        RESEARCH_PLAN_FAILED,
        f"The model's research-plan reply could not be used after {_MAX_ATTEMPTS} attempts; no template was substituted.",
        attempts=_MAX_ATTEMPTS,
        served_by=served_by,
    )
