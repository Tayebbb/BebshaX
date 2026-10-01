"""Retrieval scoring: score = w_rel·cosine + w_rec·recency + w_imp·importance.

Defaults (documented per spec): relevance dominates (0.60), recency keeps
conversations fresh (0.25, exponential half-life 48 h), importance lets
reflections outrank chit-chat (0.15). Weights are constructor-injectable on
MemoryService; these are the project defaults.
"""

from __future__ import annotations

import math

W_RELEVANCE = 0.60
W_RECENCY = 0.25
W_IMPORTANCE = 0.15
RECENCY_HALF_LIFE_HOURS = 48.0


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(x * x for x in vector))


def cosine(a: list[float], b: list[float], norm_a: float | None = None) -> float:
    """``norm_a`` lets a caller scoring one query against many rows compute it once."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = norm(a) if norm_a is None else norm_a
    norm_b = norm(b)
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def recency_decay(age_hours: float, half_life_hours: float = RECENCY_HALF_LIFE_HOURS) -> float:
    if age_hours <= 0:
        return 1.0
    return math.exp(-math.log(2) * age_hours / half_life_hours)


def combined_score(
    relevance: float,
    age_hours: float,
    importance: float,
    w_rel: float = W_RELEVANCE,
    w_rec: float = W_RECENCY,
    w_imp: float = W_IMPORTANCE,
) -> float:
    return w_rel * relevance + w_rec * recency_decay(age_hours) + w_imp * importance
