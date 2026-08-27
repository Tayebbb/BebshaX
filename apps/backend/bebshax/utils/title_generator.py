"""Deterministic study title generation without calling LLMs.

Extracts concise, research-oriented titles from product ideas, hypotheses,
and research questions, normalizing filler prefixes and sentence casing.
"""

import re
from typing import Optional

# Common conversational preamble phrases to strip out
FILLER_PREFIXES = [
    r"^i\s+(?:want|would like|am looking|need)\s+to\s+(?:build|make|create|develop|test|validate|evaluate|launch)\s+(?:an?|the)?\s*",
    r"^i'?m\s+(?:building|making|creating|developing|testing|validating|launching|designing)\s+(?:an?|the)?\s*",
    r"^we\s+want\s+to\s+(?:test|build|make|create|develop|validate|evaluate|launch)\s+(?:an?|the)?\s*",
    r"^we\s+(?:want|are building|are creating|are developing|are testing|plan to build|plan to launch)\s+(?:an?|the)?\s*",
    r"^we'?re\s+(?:building|creating|developing|testing|validating|launching)\s+(?:an?|the)?\s*",
    r"^(?:build|create|develop|test|validate|evaluate|design|launch)\s+(?:an?|the)?\s*",
    r"^(?:this is|it is|it's|this idea is)\s+(?:an?|the)?\s*",
    r"^a\s+(?:platform|system|tool|app|application|service|software|website|startup)\s+(?:for|to|that)\s*",
    r"^an?\s+(?:ai|ml|automated|smart)\s+(?:platform|system|tool|app|application|service)\s+(?:for|to|that)\s*",
    r"^(?:evaluate|explore|understand|discover)\s+(?:the|how|if)?\s*",
]

# Canonical title fallbacks per study type
CANONICAL_TYPE_TITLES = {
    "interviews": "Customer Discovery & Workflow Study",
    "landing_page_test": "Concept & Demand Validation",
    "message_testing": "Message Framing & Pitch Testing",
    "pricing": "Pricing Elasticity & WTP Analysis",
    "ab_test": "Pricing Elasticity & WTP Analysis",
}


def generate_deterministic_study_title(prompt: Optional[str], study_type: str = "interviews") -> str:
    """Generate a clean, deterministic title for a research study.

    Args:
        prompt: Raw user input / product idea / research question.
        study_type: Canonical study type identifier.

    Returns:
        A concise, capitalized title (max ~55 chars) without invoking an LLM.
    """
    if not prompt or not prompt.strip():
        return CANONICAL_TYPE_TITLES.get(study_type, "Research Study")

    cleaned = prompt.strip()

    # If prompt is very short and already title-like, format and return
    if len(cleaned) <= 30 and "\n" not in cleaned and "." not in cleaned:
        return _title_case(cleaned)

    # Take first sentence or up to first newline
    first_chunk = re.split(r"[.\n\r?!;]", cleaned)[0].strip()
    if not first_chunk:
        first_chunk = cleaned[:60].strip()

    # Strip conversational filler prefixes
    processed = first_chunk
    for pattern in FILLER_PREFIXES:
        match = re.search(pattern, processed, flags=re.IGNORECASE)
        if match:
            processed = processed[match.end():].strip()
            break

    # If stripping left nothing or too little, fallback to first chunk
    if len(processed) < 4:
        processed = first_chunk

    # Remove trailing punctuation or subordinate clauses like "and it costs..."
    processed = re.split(r"\s+(?:and it|which|that|costs?|priced at|with a price|aimed at)\s+", processed, flags=re.IGNORECASE)[0].strip()

    # Trim to ~55 characters at word boundary
    if len(processed) > 55:
        cut = processed[:55]
        last_space = cut.rfind(" ")
        if last_space > 25:
            processed = cut[:last_space]
        else:
            processed = cut
        # Truncation can leave a dangling connective ("… Decants to Students at")
        dangling = r"\s+(?:a|an|the|and|or|but|for|nor|on|at|to|from|by|with|in|of)$"
        while re.search(dangling, processed, flags=re.IGNORECASE):
            processed = re.sub(dangling, "", processed, flags=re.IGNORECASE)

    # Clean punctuation
    processed = processed.rstrip(" ,;:-.")

    if not processed or len(processed) < 3:
        return CANONICAL_TYPE_TITLES.get(study_type, "Research Study")

    return _title_case(processed)


def _title_case(text: str) -> str:
    """Format string into clean title case while preserving acronyms (AI, B2B, SaaS, BDT, etc.)."""
    minor_words = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "from", "by", "with", "in", "of"}
    known_casing = {
        "AI": "AI",
        "ML": "ML",
        "SAAS": "SaaS",
        "B2B": "B2B",
        "B2C": "B2C",
        "API": "API",
        "WTP": "WTP",
        "UI": "UI",
        "UX": "UX",
        "BDT": "BDT",
        "USD": "USD",
        "EUR": "EUR",
        "GBP": "GBP",
        "MVP": "MVP",
    }

    words = text.split()
    if not words:
        return text

    def format_token(tok: str, idx: int) -> str:
        if "-" in tok:
            subtokens = tok.split("-")
            return "-".join(format_token(st, 0 if j == 0 else 1) for j, st in enumerate(subtokens))

        upper = tok.upper()
        if upper in known_casing:
            return known_casing[upper]
        if idx > 0 and tok.lower() in minor_words:
            return tok.lower()
        return tok.capitalize()

    return " ".join(format_token(w, i) for i, w in enumerate(words))

