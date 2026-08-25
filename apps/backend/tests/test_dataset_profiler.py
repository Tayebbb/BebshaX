"""Tests for deterministic statistical dataset profiler."""

import pytest
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset


def test_profiler_calculates_exact_numeric_and_categorical_statistics():
    csv_data = b"""user_id,age,segment,monthly_budget,active
u1,20,Student,300,true
u2,22,Student,400,true
u3,25,Student,500,false
u4,30,Professional,1200,true
u5,35,Professional,1800,true
u6,40,Professional,2000,false
"""
    columns, rows = parse_dataset_bytes(csv_data, file_type="csv")
    assert columns == ["user_id", "age", "segment", "monthly_budget", "active"]
    assert len(rows) == 6

    schema, stats = profile_dataset(columns, rows)

    assert schema["row_count"] == 6
    assert schema["column_count"] == 5

    # Check numeric stats for 'age'
    age_stats = stats["numeric"]["age"]
    assert age_stats["min"] == 20
    assert age_stats["max"] == 40
    assert age_stats["median"] == 27.5
    assert age_stats["count"] == 6

    # Check numeric stats for 'monthly_budget'
    budget_stats = stats["numeric"]["monthly_budget"]
    assert budget_stats["min"] == 300
    assert budget_stats["max"] == 2000
    assert budget_stats["median"] == 850.0

    # Check categorical distribution for 'segment'
    segment_stats = stats["categorical"]["segment"]
    assert segment_stats["unique_categories"] == 2
    top_cats = {c["category"]: c["percentage"] for c in segment_stats["top_categories"]}
    assert top_cats["Student"] == 50.0
    assert top_cats["Professional"] == 50.0
