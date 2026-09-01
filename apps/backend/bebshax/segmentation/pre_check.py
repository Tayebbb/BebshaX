"""Pre-segmentation data readiness checker.

Inspects available datasets, empirical row counts, profiled variables,
and research evidence claims to determine whether a study is ready for segmentation.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class UsableVariableSummary(BaseModel):
    name: str
    type: str  # numeric, categorical, boolean, text
    source_dataset_name: str
    source_dataset_id: str
    coverage_percentage: float
    missing_percentage: float
    usefulness: str  # high, medium, low


class SegmentationReadiness(BaseModel):
    status: str  # ready, limited_data, prompt_grounded
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

    if total_records >= 20 or (total_records > 0 and claim_count >= 2) or (claim_count >= 4):
        status = "ready"
        can_run = True
        guidance = (
            f"Ready for segmentation with {len(ready_datasets)} connected dataset(s) "
            f"({total_records:,} empirical records, {len(usable_vars)} candidate variables) "
            f"and {claim_count} research evidence claim(s)."
        )
    elif total_records > 0 or claim_count > 0:
        status = "limited_data"
        can_run = True
        guidance = (
            f"Limited data available: {len(ready_datasets)} dataset(s) ({total_records:,} records) "
            f"and {claim_count} evidence claim(s). Segmentation can proceed, but results will reflect lower empirical confidence."
        )
    else:
        status = "prompt_grounded"
        can_run = True
        guidance = (
            "No uploaded empirical datasets yet — generating market segments and synthetic personas grounded on study prompt context."
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
