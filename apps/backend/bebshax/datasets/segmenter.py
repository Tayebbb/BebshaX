"""Segment Discovery & Population Distribution Engine for BebshaX.

Discovers market segments that are literally present in a dataset (a grouping
column such as role/tier/segment), with exact population shares and per-group
observed statistics. When no grouping column exists it returns no segments:
numeric partitioning is the segmentation engine's job and nothing is invented.
"""

from __future__ import annotations

import math
import statistics
from typing import Any


def discover_segments(
    columns: list[str],
    rows: list[dict[str, Any]],
    schema_metadata: dict[str, Any],
    stats: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive grounded market segments with exact population share percentages from dataset rows."""
    total_rows = len(rows)
    if total_rows == 0:
        return []

    # 1. Identify best candidate column for segmentation
    segment_candidates = [
        "segment", "user_segment", "customer_segment", "persona", "user_type",
        "role", "occupation", "category", "target_market", "tier", "plan",
        "student_type", "buyer_type", "shopper_type", "level", "group"
    ]

    selected_col: str | None = None
    lower_cols = {c.lower(): c for c in columns}

    for cand in segment_candidates:
        if cand in lower_cols:
            selected_col = lower_cols[cand]
            break

    if not selected_col:
        # Check categorical columns with reasonable cardinality (2 to 8 distinct categories)
        categorical_stats = stats.get("categorical", {})
        for col_name, cat_data in categorical_stats.items():
            u_count = cat_data.get("unique_categories", 0)
            if 2 <= u_count <= 8:
                selected_col = col_name
                break

    if not selected_col:
        # No categorical grouping variable: no derived segments. The segmentation
        # engine partitions the numeric variables statistically instead; nothing
        # is invented here (RULES.md R2).
        return []

    # Numeric/categorical companions are profiled per group ONLY when present.
    numeric_cols = [c for c in columns if c != selected_col and _is_numeric_column(rows, c)]
    text_cols = [c for c in columns if c != selected_col and c not in numeric_cols]

    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        val = str(r.get(selected_col, "")).strip()
        if not val or val.lower() in ("null", "none", "nan"):
            val = "Other / Unspecified"
        grouped_rows.setdefault(val, []).append(r)

    segments: list[dict[str, Any]] = []
    sorted_groups = sorted(grouped_rows.items(), key=lambda x: len(x[1]), reverse=True)
    for seg_idx, (seg_name, seg_rows) in enumerate(sorted_groups[:6]):
        seg_count = len(seg_rows)
        pop_share = round(seg_count / total_rows, 3)
        pop_share_pct = round((seg_count / total_rows) * 100, 1)

        observed_numeric = {c: s for c in numeric_cols if (s := _numeric_summary(seg_rows, c))}
        observed_categorical = {c: s for c in text_cols if (s := _categorical_summary(seg_rows, c))}
        constraints: dict[str, Any] = {
            "rule_description": f"{selected_col} == {seg_name!r} ({pop_share_pct}% of {total_rows} observed records)",
        }
        constraints.update(observed_numeric)
        constraints.update({c: s["dominant"] for c, s in observed_categorical.items()})

        segments.append(
            {
                "id": f"seg_{seg_idx + 1}",
                "name": seg_name,
                "population_count": seg_count,
                "population_share": pop_share,
                "population_percentage": pop_share_pct,
                "is_dataset_supported": True,
                "segmentation_feature": selected_col,
                "constraints": constraints,
                "distributions": {**observed_numeric, **{c: s["top_categories"] for c, s in observed_categorical.items()}},
                "sample_records": [{k: v for k, v in r.items() if v is not None} for r in seg_rows[:3]],
            }
        )
    return segments


def _is_numeric_column(rows: list[dict[str, Any]], col: str) -> bool:
    vals = [r.get(col) for r in rows if r.get(col) not in (None, "")]
    if not vals:
        return False
    numeric = sum(1 for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool))
    return numeric / len(vals) >= 0.9


def _numeric_summary(rows: list[dict[str, Any]], col: str) -> dict[str, Any] | None:
    vals = sorted(float(r[col]) for r in rows if isinstance(r.get(col), (int, float)) and not isinstance(r.get(col), bool))
    if not vals:
        return None
    n = len(vals)
    return {
        "count": n,
        "min": round(vals[0], 2),
        "median": round(statistics.median(vals), 2),
        "max": round(vals[-1], 2),
        "p75": round(vals[min(int(n * 0.75), n - 1)], 2),
    }


def _categorical_summary(rows: list[dict[str, Any]], col: str) -> dict[str, Any] | None:
    vals = [str(r[col]).strip() for r in rows if r.get(col) is not None and str(r.get(col)).strip()]
    if not vals:
        return None
    freq: dict[str, int] = {}
    for v in vals:
        freq[v] = freq.get(v, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return {
        "dominant": ranked[0][0],
        "top_categories": [
            {"category": k, "count": c, "percentage": round(c / len(vals) * 100, 2)} for k, c in ranked[:6]
        ],
    }


def calculate_segment_persona_distribution(
    segments: list[dict[str, Any]], requested_count: int
) -> dict[str, int]:
    """Mathematically allocate personas per segment according to population share percentages.
    
    Guarantees sum(allocated) == requested_count using largest remainder method.
    """
    if requested_count <= 0 or not segments:
        return {}

    # Exact quota calculation
    total_share = sum(s.get("population_share", 0.0) for s in segments) or 1.0
    normalized_shares = [s.get("population_share", 0.0) / total_share for s in segments]

    floored_counts: list[int] = []
    remainders: list[tuple[float, int]] = []

    for idx, share in enumerate(normalized_shares):
        raw = share * requested_count
        floored = math.floor(raw)
        floored_counts.append(floored)
        remainders.append((raw - floored, idx))

    allocated_total = sum(floored_counts)
    missing = requested_count - allocated_total

    # Distribute remainder to segments with largest fractional remainder
    remainders.sort(key=lambda x: x[0], reverse=True)
    for i in range(missing):
        seg_idx = remainders[i % len(remainders)][1]
        floored_counts[seg_idx] += 1

    distribution: dict[str, int] = {}
    for idx, seg in enumerate(segments):
        distribution[seg["id"]] = floored_counts[idx]

    return distribution
