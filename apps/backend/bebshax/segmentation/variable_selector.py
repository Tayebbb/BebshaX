"""Variable selection and ranking for market segmentation.

Extracts high-signal candidate variables (demographics, behavior, economics, needs)
from profiled datasets, filtering out constant/ID columns.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SegmentationVariable(BaseModel):
    name: str
    category: str  # economic, demographic, behavioral, preference, general
    type: str  # numeric, categorical, boolean, text
    dataset_id: str
    dataset_name: str
    missing_percentage: float
    coverage_percentage: float
    unique_count: int
    usefulness_score: float  # 0.0 to 1.0
    summary_stats: dict[str, Any] = Field(default_factory=dict)


def _categorize_variable(name: str) -> str:
    """Categorize column name into economic, demographic, behavioral, or preference."""
    lower = name.lower()
    if any(k in lower for k in ("budget", "price", "spend", "cost", "income", "fee", "payment", "salary", "bdt")):
        return "economic"
    if any(k in lower for k in ("age", "gender", "education", "occupation", "location", "city", "student", "grade", "faculty")):
        return "demographic"
    if any(k in lower for k in ("hour", "freq", "usage", "time", "daily", "weekly", "activity", "visits", "session", "device")):
        return "behavioral"
    if any(k in lower for k in ("goal", "plan", "feature", "preference", "need", "interest", "segment", "tier", "role")):
        return "preference"
    return "general"


def select_segmentation_variables(
    datasets: list[Any],
    max_variables: int = 12,
) -> list[SegmentationVariable]:
    """Select and rank high-signal candidate variables across study datasets."""
    selected: list[SegmentationVariable] = []

    for ds in datasets:
        ds_id = getattr(ds, "id", "")
        ds_name = getattr(ds, "name", "Dataset")
        meta = getattr(ds, "schema_metadata", {}) or {}
        stats = getattr(ds, "statistics", {}) or {}
        columns = meta.get("columns", []) if isinstance(meta, dict) else []

        numeric_stats = stats.get("numeric", {}) if isinstance(stats, dict) else {}
        categorical_stats = stats.get("categorical", {}) if isinstance(stats, dict) else {}

        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "text")
            missing_pct = float(col.get("missing_percentage", 0.0))
            coverage_pct = round(100.0 - missing_pct, 1)
            unique_count = int(col.get("unique_count", 0))

            lower_name = col_name.lower()

            # Skip ID columns and constant columns
            if any(id_part in lower_name for id_part in ("_id", "id_", "uuid", "guid", "token")):
                continue
            if unique_count <= 1:
                continue
            if missing_pct >= 60.0:
                continue

            category = _categorize_variable(col_name)

            # Score variable usefulness
            base_score = 0.5
            if category == "economic":
                base_score += 0.35
            elif category in ("demographic", "behavioral", "preference"):
                base_score += 0.25

            if col_type == "numeric":
                base_score += 0.1
            elif col_type == "categorical" and 2 <= unique_count <= 10:
                base_score += 0.15

            # Deduct for missing data
            penalty = (missing_pct / 100.0) * 0.4
            usefulness_score = max(0.1, min(1.0, round(base_score - penalty, 2)))

            var_summary: dict[str, Any] = {}
            if col_type == "numeric" and col_name in numeric_stats:
                var_summary = numeric_stats[col_name]
            elif col_type == "categorical" and col_name in categorical_stats:
                var_summary = categorical_stats[col_name]

            selected.append(
                SegmentationVariable(
                    name=col_name,
                    category=category,
                    type=col_type,
                    dataset_id=ds_id,
                    dataset_name=ds_name,
                    missing_percentage=missing_pct,
                    coverage_percentage=coverage_pct,
                    unique_count=unique_count,
                    usefulness_score=usefulness_score,
                    summary_stats=var_summary,
                )
            )

    # Sort descending by usefulness score
    selected.sort(key=lambda v: v.usefulness_score, reverse=True)
    return selected[:max_variables]
