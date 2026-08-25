"""Tests for segment discovery and mathematical quota allocation."""

import pytest
from bebshax.datasets.parser import parse_dataset_bytes
from bebshax.datasets.profiler import profile_dataset
from bebshax.datasets.segmenter import (
    calculate_segment_persona_distribution,
    discover_segments,
)


def test_segment_discovery_and_mathematical_quota():
    csv_data = b"""name,segment,age,budget
A,Budget-conscious,20,300
B,Budget-conscious,21,400
C,Budget-conscious,22,450
D,Budget-conscious,23,500
E,Exam-focused,24,600
F,Exam-focused,25,700
G,Working-student,26,900
H,Working-student,27,1000
I,Premium,28,2000
J,Premium,29,2500
"""
    columns, rows = parse_dataset_bytes(csv_data, file_type="csv")
    schema, stats = profile_dataset(columns, rows)
    segments = discover_segments(columns, rows, schema, stats)

    assert len(segments) >= 3
    # Check Budget-conscious segment has 40% (4/10)
    budget_seg = next(s for s in segments if "Budget-conscious" in s["name"])
    assert budget_seg["population_count"] == 4
    assert budget_seg["population_share"] == 0.4
    assert budget_seg["population_percentage"] == 40.0

    # Allocate 10 personas mathematically
    distribution = calculate_segment_persona_distribution(segments, requested_count=10)
    assert sum(distribution.values()) == 10
    assert distribution[budget_seg["id"]] == 4
