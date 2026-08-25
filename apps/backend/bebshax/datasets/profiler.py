"""Deterministic statistical profiler for BebshaX datasets.

Calculates exact counts, percentages, numeric metrics (min, max, mean, median, std, quartiles),
and categorical frequency distributions without any LLM hallucination.
"""

from __future__ import annotations

import math
import statistics
from typing import Any


def profile_dataset(columns: list[str], rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute deterministic schema metadata and descriptive statistics for a parsed dataset.

    Returns:
        (schema_metadata: dict, statistics: dict)
    """
    row_count = len(rows)
    col_count = len(columns)

    if row_count == 0:
        return {
            "columns": [],
            "row_count": 0,
            "column_count": col_count,
            "duplicate_rows": 0,
            "missing_values_percentage": 0.0,
            "warnings": ["Dataset is empty."],
        }, {
            "numeric": {},
            "categorical": {},
            "overview": {
                "row_count": 0,
                "column_count": col_count,
                "duplicate_rows": 0,
                "missing_values_percentage": 0.0,
            },
            "warnings": ["Dataset is empty."],
        }

    # Duplicate row calculation
    row_tuples: list[tuple[Any, ...]] = []
    for r in rows:
        row_tuples.append(tuple(str(r.get(c, "")) for c in columns))
    duplicate_rows_count = len(row_tuples) - len(set(row_tuples))
    duplicate_pct = round((duplicate_rows_count / row_count) * 100, 2) if row_count > 0 else 0.0

    # Extract columnar lists
    column_values: dict[str, list[Any]] = {col: [] for col in columns}
    total_cells = row_count * col_count
    total_missing_cells = 0

    for r in rows:
        for col in columns:
            val = r.get(col)
            column_values[col].append(val)
            if val is None or str(val).strip() == "":
                total_missing_cells += 1

    overall_missing_pct = round((total_missing_cells / total_cells) * 100, 2) if total_cells > 0 else 0.0

    schema_columns: list[dict[str, Any]] = []
    numeric_stats: dict[str, dict[str, Any]] = {}
    categorical_stats: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    if duplicate_rows_count > 0:
        warnings.append(f"{duplicate_rows_count} duplicate rows ({duplicate_pct}%) detected in dataset.")

    for col in columns:
        vals = column_values[col]
        non_null_vals = [v for v in vals if v is not None and str(v).strip() != ""]
        missing_count = row_count - len(non_null_vals)
        missing_pct = round((missing_count / row_count) * 100, 2) if row_count > 0 else 0.0

        if missing_pct >= 10.0:
            warnings.append(f"Column '{col}' has high missing rate of {missing_pct}% ({missing_count} missing rows).")

        # Unique values
        try:
            unique_set = set(non_null_vals)
            unique_count = len(unique_set)
        except TypeError:
            unique_count = len(set(str(v) for v in non_null_vals))

        sample_vals = [v for v in non_null_vals[:5]]
        col_type = _infer_type(non_null_vals)

        schema_columns.append({
            "name": col,
            "type": col_type,
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
            "unique_count": unique_count,
            "sample_values": sample_vals,
        })

        if col_type == "numeric":
            num_vals = [float(v) for v in non_null_vals if isinstance(v, (int, float))]
            if num_vals:
                num_vals.sort()
                n = len(num_vals)
                min_v = num_vals[0]
                max_v = num_vals[-1]
                mean_v = round(statistics.fmean(num_vals), 2)
                median_v = round(statistics.median(num_vals), 2)
                std_v = round(statistics.stdev(num_vals), 2) if n > 1 else 0.0

                # Quartiles
                p25 = round(num_vals[int(n * 0.25)], 2)
                p75 = round(num_vals[min(int(n * 0.75), n - 1)], 2)
                iqr = round(p75 - p25, 2)

                numeric_stats[col] = {
                    "count": n,
                    "min": min_v,
                    "max": max_v,
                    "mean": mean_v,
                    "median": median_v,
                    "std": std_v,
                    "p25": p25,
                    "p75": p75,
                    "iqr": iqr,
                }

                if min_v < 0 and col.lower() in ("age", "price", "budget", "salary", "income", "cost"):
                    warnings.append(f"Column '{col}' contains unexpected negative values (min: {min_v}).")
        else:
            str_vals = [str(v).strip() for v in non_null_vals if str(v).strip()]
            freq_map: dict[str, int] = {}
            for v in str_vals:
                freq_map[v] = freq_map.get(v, 0) + 1

            total_valid = len(str_vals)
            sorted_items = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)
            top_cats = [
                {
                    "category": k,
                    "count": count,
                    "percentage": round((count / total_valid) * 100, 2) if total_valid > 0 else 0.0,
                }
                for k, count in sorted_items[:10]
            ]
            percentages = {
                k: round((count / total_valid) * 100, 2)
                for k, count in sorted_items[:20]
            }

            categorical_stats[col] = {
                "count": total_valid,
                "unique_categories": len(freq_map),
                "top_categories": top_cats,
                "percentages": percentages,
            }

    schema_metadata = {
        "columns": schema_columns,
        "row_count": row_count,
        "column_count": col_count,
        "duplicate_rows": duplicate_rows_count,
        "missing_values_percentage": overall_missing_pct,
        "warnings": warnings,
    }

    stats_payload = {
        "numeric": numeric_stats,
        "categorical": categorical_stats,
        "overview": {
            "row_count": row_count,
            "column_count": col_count,
            "numeric_columns_count": len(numeric_stats),
            "categorical_columns_count": len(categorical_stats),
            "duplicate_rows": duplicate_rows_count,
            "duplicate_rows_percentage": duplicate_pct,
            "missing_values_percentage": overall_missing_pct,
        },
        "warnings": warnings,
    }

    return schema_metadata, stats_payload


def _infer_type(non_null_vals: list[Any]) -> str:
    if not non_null_vals:
        return "text"

    num_count = sum(1 for v in non_null_vals if isinstance(v, (int, float)))
    if num_count / len(non_null_vals) >= 0.9:
        return "numeric"

    bool_count = sum(1 for v in non_null_vals if isinstance(v, bool) or str(v).lower() in ("true", "false", "yes", "no"))
    if bool_count / len(non_null_vals) >= 0.9:
        return "boolean"

    unique_ratio = len(set(str(v) for v in non_null_vals)) / len(non_null_vals)
    if unique_ratio > 0.8 and len(non_null_vals) > 20:
        return "text"

    return "categorical"
