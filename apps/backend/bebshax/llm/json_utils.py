"""Shared parsing for LLM replies that are supposed to contain JSON.

Free-tier models routinely wrap JSON in markdown fences or surround it with
prose even under ``json_mode``. This module is the single home for the
fence-strip + parse logic — every call site that consumes LLM JSON goes
through :func:`parse_llm_json` instead of rolling its own fence stripper.

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


def unwrap_list(parsed: Any, *, keys: tuple[str, ...] = (), item_keys: tuple[str, ...] = ()) -> list[Any]:
    """Recover the list a prompt asked for from whatever shape the model chose.

    ``json_mode`` is OpenAI-style ``json_object`` mode: the top level MUST be an
    object, so a model asked for an array will return ``{"roles": [...]}``,
    ``{"items": [...]}`` — or, observed live, a single item object. Nothing is
    added or changed here: the model's own content is returned as a list.

    Resolution order: a list is returned as is; a dict is searched for one of
    ``keys`` holding a list, then for its only list value; a dict that carries
    one of ``item_keys`` is a single item. Anything else → ``[]``.
    """
    if isinstance(parsed, list):
        return parsed
    if not isinstance(parsed, dict):
        return []
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    list_values = [v for v in parsed.values() if isinstance(v, list)]
    if len(list_values) == 1 and not any(k in parsed for k in item_keys):
        return list_values[0]
    if item_keys and any(k in parsed for k in item_keys):
        return [parsed]
    return []
