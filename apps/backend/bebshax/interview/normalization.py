"""Deterministic reply FORMAT normalization (audit L12).

Free providers drift in output form: reasoning models leak <think> blocks,
some wrap replies in markdown fences, some answer as a script ("Alex: ...").
These are format artifacts, not answer quality — so they are normalized
deterministically here, at composition level. Actual answer quality stays with
the evaluation layer (R2/D3: never infrastructure fallback, never rewriting
content). If stripping would empty the reply, the original is returned.
"""

from __future__ import annotations

import re

# Closed reasoning blocks anywhere in the reply (deepseek-r1 style leaks).
_THINK_BLOCK = re.compile(
    r"<\s*(think|thinking|reasoning)\s*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL
)
# An unclosed opening tag at the very start: drop the tag token only —
# guessing where invisible reasoning ends would risk deleting real content.
_DANGLING_OPEN = re.compile(r"\A<\s*(think|thinking|reasoning)\s*>\s*", re.IGNORECASE)
_FENCE = re.compile(r"\A```[a-zA-Z0-9_-]*\s*\n(.*?)\n?```\s*\Z", re.DOTALL)
_GENERIC_LABELS = ("persona", "interviewer", "researcher", "assistant", "answer", "reply")


def _strip_speaker_label(text: str, persona_name: str | None) -> str:
    """Remove a script-style speaker label from the FIRST line only.

    Accepted trade-off: a persona first name that collides with an ordinary
    word ("Max: 500 taka is my limit") is stripped too — discriminating that
    would need semantic judgment, which R2/D3 forbid. First-line anchoring and
    the never-empty guard bound the blast radius.
    """
    labels = [re.escape(label) for label in _GENERIC_LABELS]
    if persona_name and persona_name.strip():
        labels.append(re.escape(persona_name.strip()))
        first = persona_name.strip().split()[0]
        if first:
            labels.append(re.escape(first))
    pattern = re.compile(
        # covers "Name: ", "**Name**: " and "**Name:** "
        r"\A(?:\*\*)?(?:" + "|".join(labels) + r")(?::\s*\*\*|\*\*\s*:|:)\s*",
        re.IGNORECASE,
    )
    m = pattern.match(text)
    if not m:
        return text
    rest = text[m.end():]
    if m.group(0).count("**") % 2 == 1:
        # consumed an unmatched opening bold ("**Alex: …**") — balance the line
        newline = rest.find("\n")
        first_line = rest if newline == -1 else rest[:newline]
        if first_line.rstrip().endswith("**"):
            balanced = first_line.rstrip()[:-2].rstrip()
            rest = balanced + (rest[newline:] if newline != -1 else "")
    return rest


def normalize_reply(text: str, persona_name: str | None = None) -> str:
    """Strip format artifacts; never mutate content; never return empty."""
    original = text.strip()
    cleaned = _THINK_BLOCK.sub("", original)
    cleaned = _DANGLING_OPEN.sub("", cleaned).strip()
    fence = _FENCE.match(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    cleaned = _strip_speaker_label(cleaned, persona_name).strip()
    return cleaned if cleaned else original
