"""Prompt placeholders: the example strings our own prompts show the model.

Observed live (ollama/llama3.2:3b): POST /api/study/copilot answered with the
literal ``"Conversational explanation and question to display to the user"`` —
the example value from ``SYSTEM_PROMPT``'s JSON template — and the acceptance
check only required a non-empty reply, so the user saw the prompt talking to
itself. Every prompt that shows a JSON example has the same failure class.

This module is a DATA TABLE (RULES.md convention), not a set of branches:
``PROMPT_PLACEHOLDERS`` lists every example string verbatim (normalised), and
``_TEMPLATE_SHAPES`` lists the bracketed-slot shapes (``[…]``, ``<…>``,
``<id>``). Add a new prompt's example strings here and add a test. Detection is
exact-match after normalisation — real sentences that merely resemble an
example (or contain the word "question") are never rejected.
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def normalise(text: str) -> str:
    """Lowercase, whitespace-collapsed form used for table lookups."""
    return " ".join(str(text).lower().split())


# Every entry is written exactly as it appears in the prompt; normalised below.
_RAW_PLACEHOLDERS: tuple[str, ...] = (
    # api/copilot.py SYSTEM_PROMPT (study design copilot)
    "Conversational explanation and question to display to the user",
    "You want to research whether [specific hypothesis about their actual business]. "
    "[Key decision they need to make]. Does this capture what you're looking for?",
    "[specific hypothesis about their actual business]",
    "[Key decision they need to make]",
    "[Specific audience description based on their context]",
    "[Core assumption to validate]",
    "ROLE TITLE IN CAPS",
    "ANOTHER ROLE",
    "Specific reason this persona type is crucial for validating the exact hypotheses in their business context",
    "Why this role is relevant",
    # api/copilot.py SUGGEST_ROLES_PROMPT
    "ROLE NAME IN CAPS (max 4 words)",
    "Specific reason this persona type is essential for validating the product hypothesis. "
    "Be concrete about what insights they provide.",
    # api/copilot.py PERSONA_GENERATION_PROMPT
    "Full Name",
    "Descriptive Archetype",
    "The [Evocative Label]",
    "Specific Job Title",
    "Realistic Income",
    "City, Country",
    "Degree Level",
    "2-3 sentence vivid description of this person in the context of the product",
    "RELEVANT LABEL",
    "Specific value relevant to the business",
    "Realistic amount for this product",
    "How they would use this product",
    "Their main concern about this product",
    "Specific Goal Related to Product",
    "What they want to achieve with this product",
    "Current Frustration",
    "What problem they currently face that this product solves",
    "Core Need",
    "What they need from this product to adopt it",
    "Brief note about realism",
    # api/studies.py script generation
    "Question 1",
    "Question 2",
    # research/report_service.py report synthesis
    "Crisp 2-3 paragraph executive summary grounded in findings",
    "Finding 1 with concrete data",
    "Finding 2",
    "Finding 3",
    "Detailed target market overview",
    "Market macro and competitive context",
    "Risk 1",
    "Risk 2",
    "Opportunity 1",
    "Opportunity 2",
    "Segment A",
    "Segment B",
    "Recommendation 1",
    "Recommendation 2",
    "Recommendation 3",
    "Synthesis of validation score and product-market fit signal",
    "Clear disclosure of synthetic simulation boundaries and dataset coverage",
    # evaluation/ai_judge.py _OUTPUT_SCHEMA
    "persona:<id>|report|interview:<id>|segment:<id>|evidence",
    "2-4 sentences",
    # generic "fill this in" markers used across the JSON examples
    "...",
    "…",
)

PROMPT_PLACEHOLDERS: frozenset[str] = frozenset(normalise(p) for p in _RAW_PLACEHOLDERS)

# Shapes of an unfilled template slot. Matched against the normalised text.
_TEMPLATE_SHAPES: tuple[re.Pattern[str], ...] = (
    # The whole text is ONE [bracketed slot]. Inner brackets mean real content
    # that merely starts and ends with a label ("[Synthetic] 3 of 3 ... [C2]").
    re.compile(r"^\[[^\[\]]*\]$"),
    re.compile(r"^<[^<>]*>$"),  # the whole text is an <angle-bracketed slot>
    re.compile(r"<id>"),  # an unfilled id, e.g. "persona:<id>"
)

_TRAILING_PUNCTUATION = ".:;,!"


def is_placeholder(text: object) -> bool:
    """True when ``text`` is one of our prompts' own example strings (exact
    match after normalisation, trailing punctuation ignored) or is entirely an
    unfilled template slot. Non-strings and empty strings are not placeholders
    — emptiness is checked by the callers already."""
    if not isinstance(text, str):
        return False
    norm = normalise(text)
    if not norm:
        return False
    if norm in PROMPT_PLACEHOLDERS or norm.rstrip(_TRAILING_PUNCTUATION) in PROMPT_PLACEHOLDERS:
        return True
    return any(shape.search(norm) for shape in _TEMPLATE_SHAPES)


def contains_placeholder(texts: Iterable[object]) -> bool:
    """True when any of ``texts`` is a placeholder."""
    return any(is_placeholder(t) for t in texts)
