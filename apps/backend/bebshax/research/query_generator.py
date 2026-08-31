"""Research query generation for study ideas.

Generates targeted research queries across Problem, Competition, Pricing,
Behavior, and Complaints using LLMService with deterministic rule fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from bebshax.llm.service import LLMService
from bebshax.llm.types import ChatMessage, LLMRequest, TaskType

logger = logging.getLogger(__name__)


def generate_deterministic_queries(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
) -> list[str]:
    """Generate 5-8 targeted search queries deterministically without LLMs."""
    clean_idea = re.sub(r"^(i'm building|we are building|i want to build|a platform for|an app for)\s+", "", idea.strip(), flags=re.IGNORECASE)
    # Extract core subject
    words = clean_idea.split()
    core_topic = " ".join(words[:6]) if len(words) > 6 else clean_idea
    audience = target_audience.strip() if target_audience else "users"

    queries = [
        f"{audience} {core_topic} pain points problems",
        f"{core_topic} competitors alternatives solutions",
        f"{core_topic} {audience} willingness to pay pricing",
        f"how {audience} currently handle {core_topic}",
        f"{core_topic} complaints friction drawbacks",
    ]

    if pricing_hypothesis and pricing_hypothesis.strip():
        clean_price = pricing_hypothesis.strip()
        queries.append(f"{core_topic} subscription cost {clean_price}")

    return queries


async def generate_research_queries(
    idea: str,
    target_audience: Optional[str] = None,
    pricing_hypothesis: Optional[str] = None,
    llm_service: Optional[LLMService] = None,
) -> list[str]:
    """Generate high-signal research queries using LLMService with deterministic fallback."""
    if not idea or not idea.strip():
        return generate_deterministic_queries("product research study", target_audience, pricing_hypothesis)

    if not llm_service:
        return generate_deterministic_queries(idea, target_audience, pricing_hypothesis)

    system_prompt = (
        "You are an expert product researcher. Given a product idea, target audience, and pricing hypothesis, "
        "generate 5 to 7 specific, high-signal research search queries across 5 categories: "
        "Problem, Competition, Pricing, User Behavior, Complaints. "
        "Output ONLY a valid JSON array of strings, e.g. [\"query 1\", \"query 2\", ...]."
    )

    user_content = f"Product Idea: {idea}\n"
    if target_audience:
        user_content += f"Target Audience: {target_audience}\n"
    if pricing_hypothesis:
        user_content += f"Pricing Hypothesis: {pricing_hypothesis}\n"

    request = LLMRequest(
        task=TaskType.STRUCTURED_OUTPUT,
        messages=[
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ],
        json_mode=True,
        temperature=0.2,
        max_output_tokens=300,
    )

    try:
        result = await llm_service.complete(request)
        text = result.text.strip()
        # Parse JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and len(parsed) >= 3:
                return [str(q).strip() for q in parsed if str(q).strip()]
    except Exception:
        # Deterministic queries are an acceptable stand-in, but the swap must
        # be visible in logs, not silent.
        logger.warning(
            "LLM research-query generation failed — using deterministic rule queries",
            exc_info=True,
        )

    return generate_deterministic_queries(idea, target_audience, pricing_hypothesis)
