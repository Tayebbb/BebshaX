"""Shared parsing for LLM replies that are supposed to contain JSON.

Free-tier models routinely wrap JSON in markdown fences or surround it with
prose even under ``json_mode``. This module is the single home for the
fence-strip + parse logic that was previously duplicated (with two divergent
regex variants) across seven call sites in five modules.

Contract: :func:`parse_llm_json` raises ``ValueError`` (``json.JSONDecodeError``
is a subclass) when no JSON payload can be recovered. Call sites keep their own
fallback semantics by catching that — control flow is unchanged from the old
inline variants; parsing is strictly more tolerant (any fence language tag,
prose before/after the payload).
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_OPEN = re.compile(r"^```[a-zA-Z0-9_-]*[ \t]*\r?\n?")
_FENCE_CLOSE = re.compile(r"\r?\n?```\s*$")
_OBJECT_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_ARRAY_BLOCK = re.compile(r"\[.*\]", re.DOTALL)


def strip_md_fences(text: str) -> str:
    """Strip one outer markdown code fence (```` ``` ```` or ```` ```json ````,
    any language tag) if present; otherwise return the stripped text unchanged."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_OPEN.sub("", cleaned, count=1)
        cleaned = _FENCE_CLOSE.sub("", cleaned, count=1).strip()
    return cleaned


def parse_llm_json(text: str) -> Any:
    """Parse the JSON payload out of an LLM reply.

    Handles bare JSON, fenced JSON (any language tag), and JSON preceded or
    followed by prose (the outermost ``{...}``/``[...]`` block wins, whichever
    opens first). Raises ``ValueError`` when nothing parseable is found.
    """
    cleaned = strip_md_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Prose-wrapped payload: whichever bracket opens first decides whether we
    # look for an object or an array first (an array of objects must not be
    # mis-parsed as its first inner object).
    first_obj = cleaned.find("{")
    first_arr = cleaned.find("[")
    if first_arr != -1 and (first_obj == -1 or first_arr < first_obj):
        patterns = (_ARRAY_BLOCK, _OBJECT_BLOCK)
    else:
        patterns = (_OBJECT_BLOCK, _ARRAY_BLOCK)
    for pattern in patterns:
        match = pattern.search(cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON payload found in LLM response ({len(text)} chars)")
