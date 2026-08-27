"""Pydantic models and data types for the evaluation module."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PersonaMetricResult(BaseModel):
    """Quality and grounding metrics for a persona object or persona dictionary."""
    persona_id: str
    is_valid: bool = True
    missing_required_fields: list[str] = Field(default_factory=list)
    grounding_ratio: float = 0.0
    grounded_attribute_count: int = 0
    total_attribute_count: int = 0
    consistency_score: float = 1.0
    contradiction_count: int = 0
    violations: list[str] = Field(default_factory=list)


class StrategyMetricResult(BaseModel):
    """Metrics recorded for a specific routing strategy during chaos simulation."""
    strategy_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    success_rate_pct: float = 0.0
    fallback_count: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    context_overflow_failures: int = 0
    avg_tokens_per_sec: float = 0.0


class OfflineEvalResult(BaseModel):
    """Evaluation output for offline dataset replay benchmarks."""
    dataset_name: str
    total_samples: int = 0
    strategy_scores: dict[str, float] = Field(default_factory=dict)
    details: list[dict[str, Any]] = Field(default_factory=list)
    # True when the benchmark dataset was absent and hardcoded synthetic
    # records were replayed instead — scores then measure nothing real and
    # must never be presented as benchmark results.
    synthetic_fallback: bool = False


class EvaluationSuiteResult(BaseModel):
    """Aggregated container for complete evaluation suite runs."""
    timestamp: str
    suite_type: str
    persona_metrics: list[PersonaMetricResult] = Field(default_factory=list)
    routing_metrics: list[StrategyMetricResult] = Field(default_factory=list)
    offline_metrics: list[OfflineEvalResult] = Field(default_factory=list)
