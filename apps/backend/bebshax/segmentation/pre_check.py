"""Pre-segmentation data readiness checker.

Inspects available datasets, empirical row counts, profiled variables,
and research evidence claims to determine whether a study is ready for segmentation.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

# Mirrors clusterer.MIN_ROWS_FOR_PARTITION (kept here to avoid an import cycle).
MIN_RECORDS_FOR_SEGMENTATION = 20


class UsableVariableSummary(BaseModel):
    name: str
    type: str  # numeric, categorical, boolean, text
    source_dataset_name: str
    source_dataset_id: str
    coverage_percentage: float
    missing_percentage: float
    usefulness: str  # high, medium, low


class SegmentationReadiness(BaseModel):
    status: str  # ready, insufficient_records, no_data
    can_run: bool
    dataset_count: int
    total_records: int
    usable_variables_count: int
    usable_variables: list[UsableVariableSummary] = Field(default_factory=list)
    evidence_claim_count: int
    supported_claims_count: int
    guidance_message: str
    study_id: str


def check_segmentation_readiness(
    study_id: str,
    datasets: list[Any],
    claims: list[Any],
    study_context: Optional[dict[str, Any]] = None,
) -> SegmentationReadiness:
    """Evaluate whether study has enough empirical datasets and evidence for segmentation."""
    total_records = 0
    usable_vars: list[UsableVariableSummary] = []
    ready_datasets = [d for d in datasets if getattr(d, "status", "") in ("ready", "processed")]

    for ds in ready_datasets:
        row_count = getattr(ds, "row_count", 0) or 0
        total_records += row_count
        meta = getattr(ds, "schema_metadata", {}) or {}
        columns = meta.get("columns", []) if isinstance(meta, dict) else []

        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "text")
            missing_pct = float(col.get("missing_percentage", 0.0))
            coverage_pct = round(100.0 - missing_pct, 1)

            # Skip ID columns and constant columns
            lower_name = col_name.lower()
            if any(id_part in lower_name for id_part in ("_id", "id_", "uuid", "guid", "token")):
                continue
            if col.get("unique_count", 0) <= 1:
                continue

            # Determine usefulness
            usefulness = "medium"
            if col_type in ("numeric", "categorical") and missing_pct < 10.0:
                if any(k in lower_name for k in ("budget", "price", "spend", "cost", "age", "segment", "tier", "role", "freq", "hour", "goal", "plan")):
                    usefulness = "high"
                else:
                    usefulness = "medium"
            elif missing_pct >= 50.0:
                usefulness = "low"

            usable_vars.append(
                UsableVariableSummary(
                    name=col_name,
                    type=col_type,
                    source_dataset_name=getattr(ds, "name", "Dataset"),
                    source_dataset_id=getattr(ds, "id", ""),
                    coverage_percentage=coverage_pct,
                    missing_percentage=missing_pct,
                    usefulness=usefulness,
                )
            )

    claim_count = len(claims)
    supported_claims_count = sum(1 for c in claims if getattr(c, "status", "") == "supported")
    has_partition_variable = any(v.type in ("numeric", "categorical") for v in usable_vars)

    # Segments are statistics over observed records. Evidence claims enrich the
    # interpretation but can never stand in for a population (RULES.md R2).
    if total_records >= MIN_RECORDS_FOR_SEGMENTATION and has_partition_variable:
        status = "ready"
        can_run = True
        guidance = (
            f"Ready for segmentation with {len(ready_datasets)} connected dataset(s) "
            f"({total_records:,} empirical records, {len(usable_vars)} candidate variables) "
            f"and {claim_count} research evidence claim(s)."
        )
    elif total_records > 0:
        status = "insufficient_records"
        can_run = False
        reason = (
            f"only {total_records:,} record(s)"
            if total_records < MIN_RECORDS_FOR_SEGMENTATION
            else "no numeric or categorical variable to partition on"
        )
        guidance = (
            f"Segmentation needs at least {MIN_RECORDS_FOR_SEGMENTATION} observed records with a usable variable "
            f"({reason} across {len(ready_datasets)} dataset(s)). Upload or import a richer dataset first."
        )
    else:
        status = "no_data"
        can_run = False
        guidance = (
            "No dataset is attached to this study, so there is no population to segment. Upload a CSV/JSON "
            "dataset or import a discovered one; BebshaX does not invent segments from the prompt"
            + (f" (the {claim_count} evidence claim(s) will be linked once segments exist)." if claim_count else ".")
        )

    return SegmentationReadiness(
        status=status,
        can_run=can_run,
        dataset_count=len(ready_datasets),
        total_records=total_records,
        usable_variables_count=len(usable_vars),
        usable_variables=usable_vars,
        evidence_claim_count=claim_count,
        supported_claims_count=supported_claims_count,
        guidance_message=guidance,
        study_id=study_id,
    )
