"""Deterministic statistical clusterer over the study's observed rows.

Computes exact groupings, population counts, percentages, numeric quantiles and
categorical frequencies from the dataset records themselves. Nothing here is
assumed: no default age ranges, budgets, currencies or archetypes — without
usable rows the caller receives an explicit ``segmentation_requires_data``.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Optional
from pydantic import BaseModel, Field

from bebshax.segmentation.variable_selector import SegmentationVariable
from bebshax.utils.explicit_failures import InsufficientInput


class ClusterDistribution(BaseModel):
    cluster_label: str
    population_count: int
    population_percentage: float
    confidence_score: float
    status: str  # data_backed, inference_assisted, insufficient_evidence
    characteristics: dict[str, Any] = Field(default_factory=dict)
    variable_distributions: dict[str, Any] = Field(default_factory=dict)
    distinctive_traits: list[str] = Field(default_factory=list)


def _percentile(values: list[float], p: float) -> float:
    """Calculate p-th percentile (0..100) on sorted non-empty list of floats."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return round(d0 + d1, 2)


def _compute_numeric_stats(values: list[float]) -> dict[str, Any]:
    """Compute deterministic distribution statistics on list of numbers."""
    if not values:
        return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "p25": 0, "p75": 0, "iqr": 0, "std": 0}
    clean = sorted(values)
    count = len(clean)
    min_v = clean[0]
    max_v = clean[-1]
    mean_v = sum(clean) / count
    p25 = _percentile(clean, 25)
    median_v = _percentile(clean, 50)
    p75 = _percentile(clean, 75)
    iqr = round(p75 - p25, 2)

    variance = sum((x - mean_v) ** 2 for x in clean) / count
    std_v = math.sqrt(variance)

    return {
        "count": count,
        "min": round(min_v, 2),
        "max": round(max_v, 2),
        "mean": round(mean_v, 2),
        "median": round(median_v, 2),
        "p25": round(p25, 2),
        "p75": round(p75, 2),
        "iqr": round(iqr, 2),
        "std": round(std_v, 2),
    }


def _compute_categorical_stats(values: list[str]) -> dict[str, Any]:
    """Compute deterministic categorical distribution frequencies."""
    if not values:
        return {"count": 0, "unique_categories": 0, "top_categories": [], "percentages": {}}
    freqs: dict[str, int] = {}
    for v in values:
        freqs[v] = freqs.get(v, 0) + 1
    total = len(values)
    sorted_cats = sorted(freqs.items(), key=lambda x: x[1], reverse=True)
    top_cats = [
        {"category": cat, "count": cnt, "percentage": round((cnt / total) * 100, 2)}
        for cat, cnt in sorted_cats[:6]
    ]
    percentages = {cat: round((cnt / total) * 100, 2) for cat, cnt in freqs.items()}
    return {
        "count": total,
        "unique_categories": len(freqs),
        "top_categories": top_cats,
        "percentages": percentages,
    }


SEGMENTATION_REQUIRES_DATA = "segmentation_requires_data"

# Statistical partitioning only makes sense with a minimum number of observed
# records per band; below this the "segments" would be noise dressed as data.
MIN_ROWS_FOR_PARTITION = 20
MIN_ROWS_PER_BAND = 5
_MAX_CLUSTERS = 6


def load_dataset_rows(dataset: Any) -> list[dict[str, Any]]:
    """Rows persisted by the dataset pipeline (``file_path`` JSON list). Missing
    or unreadable files yield ``[]`` — the caller decides whether that is fatal."""
    path = getattr(dataset, "file_path", None)
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except (OSError, ValueError):
        return []
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _band_edges(sorted_values: list[float], k: int) -> list[tuple[float, float]]:
    """k quantile bands (lower, upper) over the observed values."""
    edges = [_percentile(sorted_values, 100.0 * i / k) for i in range(k + 1)]
    return [(edges[i], edges[i + 1]) for i in range(k)]


def _assign_band(value: float, bands: list[tuple[float, float]]) -> int:
    for i, (lo, hi) in enumerate(bands):
        is_last = i == len(bands) - 1
        if lo <= value < hi or (is_last and value <= hi):
            return i
    return len(bands) - 1


def _row_band(row: dict[str, Any], primary: str, bands: list[tuple[float, float]]) -> Optional[int]:
    value = _numeric(row.get(primary))
    return None if value is None else _assign_band(value, bands)


def _profile_rows(rows: list[dict[str, Any]], variables: list[SegmentationVariable]) -> dict[str, Any]:
    """Distributions of every selected variable inside one band — computed, never assumed."""
    dists: dict[str, Any] = {}
    for var in variables:
        raw = [r.get(var.name) for r in rows if r.get(var.name) not in (None, "")]
        if not raw:
            continue
        if var.type == "numeric":
            nums = [v for v in (_numeric(x) for x in raw) if v is not None]
            if nums:
                dists[var.name] = _compute_numeric_stats(nums)
        else:
            dists[var.name] = _compute_categorical_stats([str(x).strip() for x in raw])
    return dists


def _traits_from_distributions(dists: dict[str, Any], share_pct: float) -> list[str]:
    traits = [f"Population share: {share_pct}% of observed records"]
    for name, d in list(dists.items())[:4]:
        if "median" in d:
            traits.append(f"{name}: {d['min']:g}–{d['max']:g} (median {d['median']:g})")
        elif d.get("top_categories"):
            top = d["top_categories"][0]
            traits.append(f"{name}: mostly {top['category']} ({top['percentage']}%)")
    return traits


def _explicit_segment_clusters(
    explicit_segments: list[dict[str, Any]], total_records: int
) -> list[ClusterDistribution]:
    """Strategy A — segments the dataset pipeline already derived from real rows
    (categorical grouping). Every derived group is kept so the population stays
    complete; only observed constraints are carried, nothing is back-filled."""
    subset = explicit_segments[:_MAX_CLUSTERS]
    total_pop = sum(int(s.get("population_count") or 0) for s in subset) or total_records
    clusters: list[ClusterDistribution] = []
    for idx, seg in enumerate(subset):
        pop_count = int(seg.get("population_count") or 0)
        pop_pct = seg.get("population_percentage")
        if pop_pct is None:
            pop_pct = round((pop_count / total_pop) * 100, 1) if total_pop else 0.0
        constraints = seg.get("constraints") or {}
        observed = {k: v for k, v in constraints.items() if v not in (None, "", [], {})}
        characteristics: dict[str, Any] = {
            "name_hint": seg.get("name") or f"Segment {idx + 1}",
            "observed_constraints": observed,
            "rule_description": constraints.get("rule_description", ""),
            "confidence_basis": "population_size_heuristic",
            "partition_method": "categorical_grouping",
        }
        clusters.append(
            ClusterDistribution(
                cluster_label=f"cluster_{idx}",
                population_count=pop_count,
                population_percentage=float(pop_pct),
                confidence_score=0.92 if pop_count >= 100 else 0.85,
                status="data_backed",
                characteristics=characteristics,
                variable_distributions={"segment_name": seg.get("name"), **(seg.get("distributions") or {})},
                distinctive_traits=[f"{k}: {v}" for k, v in observed.items() if not isinstance(v, (dict, list))][:4],
            )
        )
    return clusters


def cluster_dataset_populations(
    datasets: list[Any],
    variables: list[SegmentationVariable],
    claims: list[Any],
    study_context: Optional[dict[str, Any]] = None,
    desired_clusters: Optional[int] = None,
    rows_by_dataset: Optional[dict[str, list[dict[str, Any]]]] = None,
) -> list[ClusterDistribution]:
    """Partition the study's OBSERVED population into 2–6 data-backed clusters.

    Strategy A: segments already derived by the dataset pipeline (categorical
    grouping of real rows). Strategy B: quantile bands on the highest-ranked
    numeric variable over the actual rows, with every other selected variable
    profiled inside each band. No rows and no derived segments →
    ``InsufficientInput(segmentation_requires_data)``; there is no archetype
    list to fall back on (RULES.md R2).
    """
    total_records = sum(int(getattr(d, "row_count", 0) or 0) for d in datasets)

    explicit_segments: list[dict[str, Any]] = []
    for ds in datasets:
        segs = getattr(ds, "segments", []) or []
        if isinstance(segs, list) and len(segs) >= 2:
            explicit_segments.extend(s for s in segs if isinstance(s, dict))

    rows: list[dict[str, Any]] = []
    for ds in datasets:
        ds_id = getattr(ds, "id", "")
        rows.extend((rows_by_dataset or {}).get(ds_id) or load_dataset_rows(ds))
    numeric_vars = [v for v in variables if v.type == "numeric"]
    primary = next((v for v in numeric_vars if v.category == "economic"), None) or (numeric_vars[0] if numeric_vars else None)
    can_partition = primary is not None and len(rows) >= MIN_ROWS_FOR_PARTITION

    # Derived categorical groups win unless the caller asked for a different
    # number of clusters AND a statistical partition is possible.
    if explicit_segments and not (desired_clusters and desired_clusters != len(explicit_segments) and can_partition):
        return _explicit_segment_clusters(explicit_segments, total_records)

    # Strategy B — real rows, real quantiles.
    if not can_partition:
        raise InsufficientInput(
            SEGMENTATION_REQUIRES_DATA,
            "Segmentation needs an imported dataset with at least "
            f"{MIN_ROWS_FOR_PARTITION} records and one numeric variable (found {len(rows)} usable records"
            f"{'' if primary else ', no numeric variable'}). Upload or import a dataset before segmenting; "
            "BebshaX does not invent segments.",
        )

    values = sorted(v for v in (_numeric(r.get(primary.name)) for r in rows) if v is not None)
    if len(values) < MIN_ROWS_FOR_PARTITION or values[0] == values[-1]:
        raise InsufficientInput(
            SEGMENTATION_REQUIRES_DATA,
            f"Variable '{primary.name}' has too little variation across {len(values)} records to form segments.",
        )

    if desired_clusters and 2 <= desired_clusters <= _MAX_CLUSTERS:
        k = desired_clusters
    else:
        k = 4 if len(values) >= 1000 else (3 if len(values) >= 100 else 2)
    k = max(2, min(k, len(values) // MIN_ROWS_PER_BAND))

    bands = _band_edges(values, k)
    # Merge bands whose edges collapsed onto the same value (heavily tied data).
    merged: list[tuple[float, float]] = []
    for lo, hi in bands:
        if merged and merged[-1][1] == lo and lo == hi:
            continue
        merged.append((lo, hi))
    bands = merged

    band_rows: list[list[dict[str, Any]]] = [[] for _ in bands]
    for row in rows:
        idx = _row_band(row, primary.name, bands)
        if idx is not None:
            band_rows[idx].append(row)
    observed_total = sum(len(b) for b in band_rows)

    clusters: list[ClusterDistribution] = []
    label_idx = 0
    for (lo, hi), members in zip(bands, band_rows):
        if not members:
            continue
        share_pct = round(len(members) / observed_total * 100, 1)
        dists = _profile_rows(members, variables)
        primary_stats = dists.get(primary.name) or _compute_numeric_stats(
            [v for v in (_numeric(r.get(primary.name)) for r in members) if v is not None]
        )
        characteristics = {
            "name_hint": f"{primary.name} {lo:g}–{hi:g}",
            "partition_method": "quantile_bands",
            "partition_variable": primary.name,
            "band": {"lower": lo, "upper": hi},
            "observed": dists,
            "confidence_basis": "population_size_heuristic",
        }
        clusters.append(
            ClusterDistribution(
                cluster_label=f"cluster_{label_idx}",
                population_count=len(members),
                population_percentage=share_pct,
                confidence_score=0.90 if len(members) >= 100 else 0.80,
                status="data_backed",
                characteristics=characteristics,
                variable_distributions={**dists, primary.name: primary_stats},
                distinctive_traits=_traits_from_distributions({primary.name: primary_stats, **dists}, share_pct),
            )
        )
        label_idx += 1
    return clusters
