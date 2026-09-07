"""Cheap lexical checks on cited evidence (persona provenance hardening).

Two questions a citation must survive before a claim may be OBSERVED:

1. Grounding gate — does the claim share at least one content token with any
   evidence text it cites? "Fly to Mars" citing a stapler review is a
   citation, not grounding.
2. Contested evidence — do the cited items disagree on a numeric slot (age,
   price/income, counts)? Two records stating 24 and 41 years cannot both
   ground one claim as observed fact.

Deterministic, table-driven, no LLM. Extend the slot table + add a test.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MIN_TOKEN_LEN = 4
# Non-Latin scripts (Bangla, Arabic, …) pack meaning into shorter strings and
# have no English stoplist here, so a 2-char floor is the honest equivalent.
MIN_TOKEN_LEN_NON_ASCII = 2

# Function words and research boilerplate that must not count as grounding.
STOPWORDS: frozenset[str] = frozenset({
    "about", "above", "after", "again", "against", "also", "although", "always", "among",
    "another", "around", "because", "been", "before", "being", "below", "between", "both",
    "cannot", "could", "does", "doing", "done", "down", "during", "each", "either", "else",
    "even", "ever", "every", "from", "further", "have", "having", "here", "hers", "herself",
    "himself", "into", "itself", "just", "like", "made", "make", "many", "more", "most",
    "much", "must", "myself", "never", "often", "once", "only", "other", "ours", "over",
    "really", "same", "shall", "should", "since", "some", "still", "such", "than", "that",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they", "thing",
    "things", "this", "those", "though", "through", "thus", "under", "until", "upon",
    "very", "want", "wants", "were", "what", "when", "where", "whether", "which", "while",
    "will", "with", "within", "without", "would", "your", "yours", "yourself",
    # research boilerplate: present in nearly every record AND nearly every claim
    "user", "users", "people", "person", "persona", "customer", "customers", "respondent",
})

# Split on whitespace + ASCII punctuation only, so combining vowel signs in
# Bangla/Devanagari (Unicode category M*, not matched by \w) stay inside the word.
_TOKEN_SPLIT_RE = re.compile(r"[\s!\"#$%&'()*+,./:;<=>?@\[\\\]^_`{|}~\u2013\u2014\u201c\u201d\u2018\u2019\u0964]+")

# Numeric slots. Each value in a slot is compared only against values of the
# same slot (and, for counts, the same unit).
_AGE_RE = re.compile(
    r"\b(\d{2})[- ]?(?:years?[- ]old|yrs?\b|yo\b|years?\s+of\s+age)|\bage[d:]?\s*(\d{2})\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(?:৳|BDT|Tk\.?)\s?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(%|(?:percent|times|people|hours?|hrs|minutes?|mins|days?|weeks?|"
    r"months?|orders?|items?|visits?|km|kg)\b)",
    re.IGNORECASE,
)

_COUNT_UNIT_ALIASES = {
    "percent": "%", "hour": "hours", "hrs": "hours", "minute": "minutes", "mins": "minutes",
    "day": "days", "week": "weeks", "month": "months", "order": "orders", "item": "items",
    "visit": "visits",
}

# Slots that describe WHO the evidence is about; a disagreement here contests
# every claim resting on those sources, whatever the claim says.
IDENTITY_SLOTS: frozenset[str] = frozenset({"age"})


def content_tokens(text: str) -> set[str]:
    """Lower-cased word tokens that are not stopwords or bare numbers: ASCII
    words need length ≥4, non-ASCII words length ≥2 (script-aware). Naive
    plural folding so "deliveries" grounds "delivery"."""
    tokens: set[str] = set()
    for raw in _TOKEN_SPLIT_RE.split((text or "").lower()):
        if not raw or raw.isdigit():
            continue
        if raw.isascii():
            if len(raw) < MIN_TOKEN_LEN or raw in STOPWORDS:
                continue
            tokens.add(raw)
            if raw.endswith("ies") and len(raw) > 4:
                tokens.add(raw[:-3] + "y")
            elif raw.endswith("s") and not raw.endswith("ss"):
                tokens.add(raw[:-1])
        elif len(raw) >= MIN_TOKEN_LEN_NON_ASCII:
            tokens.add(raw)
    return tokens


def shares_content_token(claim_text: str, evidence_texts: Iterable[str]) -> bool:
    """Grounding gate: the claim overlaps lexically with at least one cited text."""
    claim_tokens = content_tokens(claim_text)
    if not claim_tokens:
        return False
    return any(claim_tokens & content_tokens(text) for text in evidence_texts)


def numeric_slots(text: str) -> dict[str, set[str]]:
    """{slot: values} detected in ``text``. Slots: ``age``, ``price``, ``count:<unit>``."""
    slots: dict[str, set[str]] = {}
    for match in _AGE_RE.finditer(text or ""):
        value = match.group(1) or match.group(2)
        slots.setdefault("age", set()).add(str(int(value)))
    for match in _MONEY_RE.finditer(text or ""):
        try:
            amount = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        slots.setdefault("price", set()).add(f"{amount:g}")
    for match in _COUNT_RE.finditer(text or ""):
        unit = match.group(2).lower()
        unit = _COUNT_UNIT_ALIASES.get(unit, unit)
        slots.setdefault(f"count:{unit}", set()).add(match.group(1))
    return slots


def contested_slots(
    evidence_texts: Iterable[str], *, claim_text: str | None = None
) -> list[str]:
    """Slots on which two cited texts state disjoint values.

    Returns warning-ready slot names (``age``, ``price``, ``count``), sorted
    and de-duplicated. A slot mentioned by only one text is never contested.
    When ``claim_text`` is given, non-identity slots only count if the claim
    itself asserts them: two reviewers disagreeing on "2 hours" vs "5 hours"
    does not contest a claim that says nothing about hours. Identity slots
    (``IDENTITY_SLOTS``) always count — sources that disagree on who the
    person is cannot jointly ground one persona's claim as observed fact.
    """
    per_text = [numeric_slots(text) for text in evidence_texts]
    claim_slots = numeric_slots(claim_text) if claim_text is not None else None
    contested: set[str] = set()
    slot_names = {slot for slots in per_text for slot in slots}
    for slot in slot_names:
        name = slot.split(":", 1)[0]
        if claim_slots is not None and name not in IDENTITY_SLOTS and slot not in claim_slots:
            continue
        holders = [slots[slot] for slots in per_text if slot in slots]
        if len(holders) < 2:
            continue
        for i, left in enumerate(holders):
            if any(left.isdisjoint(right) for right in holders[i + 1 :]):
                contested.add(name)
                break
    return sorted(contested)


__all__ = [
    "IDENTITY_SLOTS",
    "STOPWORDS",
    "content_tokens",
    "contested_slots",
    "numeric_slots",
    "shares_content_token",
]
