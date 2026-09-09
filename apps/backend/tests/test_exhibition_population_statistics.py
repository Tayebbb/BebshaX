"""Population conservation and invariance contracts over in-memory source rows."""

from types import SimpleNamespace
from typing import Any

import pytest

from bebshax.datasets.segmenter import (
    calculate_segment_persona_distribution,
    discover_segments,
)
from bebshax.segmentation.clusterer import (
    SEGMENTATION_REQUIRES_DATA,
    ClusterDistribution,
    cluster_dataset_populations,
)
from bebshax.segmentation.variable_selector import SegmentationVariable
from bebshax.utils.explicit_failures import InsufficientInput


def _discover(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = list(dict.fromkeys(column for row in rows for column in row))
    return discover_segments(columns, rows, {}, {})


def _explicit_clusters(
    segments: list[dict[str, Any]], total_records: int
) -> list[ClusterDistribution]:
    dataset = SimpleNamespace(
        id="observed", row_count=total_records, segments=segments, file_path=None
    )
    return cluster_dataset_populations([dataset], [], [])


@pytest.fixture
def categorical_rows() -> list[dict[str, Any]]:
    return [
        {"role": f"Observed role {group_index}"}
        for group_index in range(7)
        for _ in range(5)
    ] + [{}, {"role": None}, {"role": ""}, {"role": "  "}, {"role": "NaN"}]


def test_combined_datasets_use_the_pooled_population_denominator() -> None:
    rows_by_dataset = {
        "small": [{"role": "Small A" if index < 10 else "Small B"} for index in range(20)],
        "large": [{"role": "Large A" if index < 30 else "Large B"} for index in range(60)],
    }
    datasets = [
        SimpleNamespace(
            id=dataset_id, row_count=len(rows), segments=_discover(rows), file_path=None
        )
        for dataset_id, rows in rows_by_dataset.items()
    ]

    clusters = cluster_dataset_populations(
        datasets, [], [], rows_by_dataset=rows_by_dataset
    )

    assert len(clusters) == 4
    assert {cluster.characteristics["name_hint"]: cluster.population_count for cluster in clusters} == {
        "Small A": 10, "Small B": 10, "Large A": 30, "Large B": 30,
    }
    assert {
        cluster.characteristics["name_hint"]: cluster.population_percentage
        for cluster in clusters
    } == pytest.approx({"Small A": 12.5, "Small B": 12.5, "Large A": 37.5, "Large B": 37.5})
    assert sum(cluster.population_count for cluster in clusters) == 80
    assert sum(cluster.population_percentage for cluster in clusters) == pytest.approx(100.0)


def test_discovery_keeps_all_observed_groups_including_missing(
    categorical_rows: list[dict[str, Any]],
) -> None:
    expected_counts = {f"Observed role {index}": 5 for index in range(7)}
    expected_counts["Other / Unspecified"] = 5

    segments = _discover(categorical_rows)

    assert len(segments) == len(expected_counts)
    assert {segment["name"]: segment["population_count"] for segment in segments} == expected_counts
    assert sum(segment["population_count"] for segment in segments) == len(categorical_rows)
    assert sum(segment["population_percentage"] for segment in segments) == pytest.approx(100.0)
    assert sum(segment["population_share"] for segment in segments) == pytest.approx(1.0)
    for segment in segments:
        assert segment["population_percentage"] == pytest.approx(12.5)
        assert segment["segmentation_feature"] == "role"
        assert segment["is_dataset_supported"] is True
        assert f"role == {segment['name']!r}" in segment["constraints"]["rule_description"]


def test_explicit_clustering_keeps_all_supplied_observed_groups() -> None:
    segments = [
        {
            "name": f"Observed role {index}",
            "population_count": count,
            "constraints": {"role": f"Observed role {index}"},
        }
        for index, count in enumerate([10, 5, 5, 5, 5, 5, 5])
    ]

    clusters = _explicit_clusters(segments, total_records=40)

    assert len(clusters) == len(segments)
    assert {
        cluster.characteristics["name_hint"]: cluster.population_count for cluster in clusters
    } == {segment["name"]: segment["population_count"] for segment in segments}
    assert sum(cluster.population_count for cluster in clusters) == 40
    assert sum(cluster.population_percentage for cluster in clusters) == pytest.approx(100.0)
    for cluster in clusters:
        name = cluster.characteristics["name_hint"]
        assert cluster.characteristics["observed_constraints"] == {"role": name}
        assert cluster.variable_distributions["segment_name"] == name
        assert cluster.population_percentage == pytest.approx(cluster.population_count / 40 * 100)
        assert cluster.status == "data_backed"


@pytest.mark.parametrize("transformation", ["reverse_rows", "duplicate_all_rows", "irrelevant_columns"])
def test_categorical_population_and_identity_are_invariant_to_input_transformations(
    categorical_rows: list[dict[str, Any]], transformation: str,
) -> None:
    original_segments = _discover(categorical_rows)
    original_clusters = _explicit_clusters(original_segments, len(categorical_rows))
    multiplier = 1
    if transformation == "reverse_rows":
        transformed_rows = list(reversed(categorical_rows))
    elif transformation == "duplicate_all_rows":
        transformed_rows = [dict(row) for row in categorical_rows * 2]
        multiplier = 2
    else:
        transformed_rows = [
            {**row, "audit_note": "irrelevant", "audit_number": index}
            for index, row in enumerate(categorical_rows)
        ]

    transformed_segments = _discover(transformed_rows)
    transformed_clusters = _explicit_clusters(transformed_segments, len(transformed_rows))

    assert {
        segment["name"]: (
            segment["id"], segment["population_count"],
            segment["population_percentage"], segment["population_share"],
        )
        for segment in transformed_segments
    } == {
        segment["name"]: (
            segment["id"], segment["population_count"] * multiplier,
            segment["population_percentage"], segment["population_share"],
        )
        for segment in original_segments
    }
    assert {
        cluster.characteristics["name_hint"]: (
            cluster.cluster_label, cluster.population_count, cluster.population_percentage,
        )
        for cluster in transformed_clusters
    } == {
        cluster.characteristics["name_hint"]: (
            cluster.cluster_label, cluster.population_count * multiplier, cluster.population_percentage,
        )
        for cluster in original_clusters
    }


@pytest.mark.parametrize("include_dataset_local_shares", [False, True])
@pytest.mark.parametrize(
    ("requested_count", "expected_counts"),
    [(8, [1, 1, 3, 3]), (7, [1, 1, 3, 2])],
)
def test_quota_allocation_uses_counts_not_dataset_local_or_missing_shares(
    include_dataset_local_shares: bool, requested_count: int, expected_counts: list[int],
) -> None:
    segments: list[dict[str, Any]] = [
        {"id": f"seg_{index}", "population_count": count}
        for index, count in enumerate([10, 10, 30, 30])
    ]
    if include_dataset_local_shares:
        segments = [
            {**segment, "population_share": 0.5, "population_percentage": 50.0}
            for segment in segments
        ]

    allocation = calculate_segment_persona_distribution(segments, requested_count)

    assert allocation == {f"seg_{index}": count for index, count in enumerate(expected_counts)}
    assert sum(allocation.values()) == requested_count


@pytest.mark.parametrize("invalid_count", [-1, 1.5, float("nan"), float("inf"), True])
def test_quota_allocation_rejects_invalid_observed_counts(invalid_count: int | float) -> None:
    segments = [
        {"id": "invalid", "population_count": invalid_count, "population_share": 0.5},
        {"id": "valid", "population_count": 3, "population_share": 0.5},
    ]

    with pytest.raises(ValueError, match="population_count"):
        calculate_segment_persona_distribution(segments, 2)


@pytest.mark.parametrize("missing_count", [{}, {"population_count": None}])
def test_quota_allocation_uses_shares_when_counts_are_incomplete(missing_count: dict[str, Any]) -> None:
    segments = [
        {"id": "counted", "population_count": 10, "population_share": 0.5},
        {"id": "uncounted", "population_share": 0.5, **missing_count},
    ]

    assert calculate_segment_persona_distribution(segments, 10) == {"counted": 5, "uncounted": 5}


@pytest.mark.parametrize(
    ("counts", "requested_count", "expected"),
    [([0, 5], 3, {"seg_0": 0, "seg_1": 3}), ([1, 2, 3], 1, {"seg_0": 0, "seg_1": 0, "seg_2": 1})],
)
def test_quota_allocation_conserves_small_requests_and_zero_groups(
    counts: list[int], requested_count: int, expected: dict[str, int],
) -> None:
    segments = [{"id": f"seg_{index}", "population_count": count} for index, count in enumerate(counts)]

    assert calculate_segment_persona_distribution(segments, requested_count) == expected


@pytest.mark.parametrize("desired_clusters", [2, 3, 4, 5, 6])
def test_numeric_partition_keeps_requested_two_to_six_cluster_behavior(desired_clusters: int) -> None:
    rows = [{"monthly_budget": index} for index in range(60)]
    dataset = SimpleNamespace(id="numeric", row_count=len(rows), segments=[], file_path=None)
    variable = SegmentationVariable(
        name="monthly_budget", category="economic", type="numeric",
        dataset_id="numeric", dataset_name="Numeric fixture",
        missing_percentage=0.0, coverage_percentage=100.0,
        unique_count=len(rows), usefulness_score=1.0,
    )

    clusters = cluster_dataset_populations(
        [dataset], [variable], [], desired_clusters=desired_clusters,
        rows_by_dataset={"numeric": rows},
    )

    assert len(clusters) == desired_clusters
    assert sum(cluster.population_count for cluster in clusters) == len(rows)
    assert sum(cluster.population_percentage for cluster in clusters) == pytest.approx(100.0, abs=0.5)
    assert all(cluster.characteristics["partition_method"] == "quantile_bands" for cluster in clusters)


def test_absent_observations_do_not_produce_invented_segments() -> None:
    assert _discover([]) == []
    with pytest.raises(InsufficientInput) as error:
        cluster_dataset_populations([], [], [])
    assert error.value.error_code == SEGMENTATION_REQUIRES_DATA