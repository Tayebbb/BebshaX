"""Tests for the Market Segmentation Engine: readiness, variable selection,
deterministic clustering, distribution formulas, and LLM interpretation.
"""

import pytest
from datetime import datetime, timezone
from bebshax.db.models import DatasetSources, EvidenceClaims, Studies
from bebshax.segmentation.clusterer import (
    _compute_numeric_stats,
    _compute_categorical_stats,
    cluster_dataset_populations,
)
from bebshax.segmentation.interpreter import (
    _deterministic_interpret_cluster,
    interpret_market_segments,
)
from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.variable_selector import select_segmentation_variables


def test_deterministic_numeric_statistics():
    """Verify exact calculation of min, median, max, IQR, and standard deviation."""
    values = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0]
    stats = _compute_numeric_stats(values)
    assert stats["count"] == 9
    assert stats["min"] == 100.0
    assert stats["max"] == 900.0
    assert stats["mean"] == 500.0
    assert stats["median"] == 500.0
    assert stats["p25"] == 300.0
    assert stats["p75"] == 700.0
    assert stats["iqr"] == 400.0
    assert stats["std"] > 0


def test_deterministic_categorical_statistics():
    """Verify categorical frequency counts and percentages."""
    cats = ["Student", "Student", "Student", "Working", "Working", "Executive"]
    stats = _compute_categorical_stats(cats)
    assert stats["count"] == 6
    assert stats["unique_categories"] == 3
    assert stats["percentages"]["Student"] == 50.0
    assert stats["percentages"]["Working"] == 33.33
    assert stats["percentages"]["Executive"] == 16.67


def test_segmentation_readiness_states():
    """Verify ready, limited_data, and no_data states."""
    # State 1: No data
    no_data_res = check_segmentation_readiness("study_1", [], [])
    assert no_data_res.status == "no_data"
    assert no_data_res.can_run is False

    # State 2: Limited data (small sample or single claim)
    dummy_claim = EvidenceClaims(id="clm_1", claim_text="Students want cheap tools", status="supported")
    lim_res = check_segmentation_readiness("study_1", [], [dummy_claim])
    assert lim_res.status == "limited_data"
    assert lim_res.can_run is True

    # State 3: Ready with dataset and claims
    dummy_ds = DatasetSources(
        id="ds_1",
        name="Student Survey",
        status="ready",
        row_count=1200,
        schema_metadata={
            "columns": [
                {"name": "student_id", "type": "text", "missing_percentage": 0, "unique_count": 1200},
                {"name": "monthly_budget", "type": "numeric", "missing_percentage": 1.2, "unique_count": 45},
                {"name": "tech_familiarity", "type": "categorical", "missing_percentage": 0, "unique_count": 3},
            ]
        },
    )
    ready_res = check_segmentation_readiness("study_1", [dummy_ds], [dummy_claim, dummy_claim, dummy_claim, dummy_claim])
    assert ready_res.status == "ready"
    assert ready_res.can_run is True
    assert ready_res.total_records == 1200
    assert ready_res.usable_variables_count == 2


def test_variable_selector_filters_ids_and_ranks():
    """Verify variable selector excludes ID columns and scores usefulness."""
    dummy_ds = DatasetSources(
        id="ds_1",
        name="Student Survey",
        status="ready",
        schema_metadata={
            "columns": [
                {"name": "user_id", "type": "text", "missing_percentage": 0, "unique_count": 500},
                {"name": "uuid", "type": "text", "missing_percentage": 0, "unique_count": 500},
                {"name": "monthly_budget", "type": "numeric", "missing_percentage": 2.0, "unique_count": 30},
                {"name": "age", "type": "numeric", "missing_percentage": 0.5, "unique_count": 12},
                {"name": "constant_flag", "type": "categorical", "missing_percentage": 0, "unique_count": 1},
            ]
        },
        statistics={
            "numeric": {"monthly_budget": {"min": 200, "median": 450, "max": 1200}, "age": {"min": 18, "median": 21, "max": 26}}
        },
    )
    vars_selected = select_segmentation_variables([dummy_ds])
    names = [v.name for v in vars_selected]
    assert "user_id" not in names
    assert "uuid" not in names
    assert "constant_flag" not in names
    assert "monthly_budget" in names
    assert "age" in names

    budget_var = next(v for v in vars_selected if v.name == "monthly_budget")
    assert budget_var.category == "economic"
    assert budget_var.usefulness_score >= 0.7


def test_cluster_dataset_populations_deterministic_quantiles():
    """Verify deterministic quantile clustering on numeric variables."""
    dummy_ds = DatasetSources(
        id="ds_1",
        name="Empirical Budget Survey",
        status="ready",
        row_count=1000,
        schema_metadata={
            "columns": [
                {"name": "budget", "type": "numeric", "missing_percentage": 0, "unique_count": 100},
                {"name": "age", "type": "numeric", "missing_percentage": 0, "unique_count": 10},
            ]
        },
        statistics={
            "numeric": {
                "budget": {"min": 200, "p25": 350, "median": 500, "p75": 850, "max": 2000, "mean": 600}
            }
        },
    )
    variables = select_segmentation_variables([dummy_ds])
    clusters = cluster_dataset_populations([dummy_ds], variables, [], desired_clusters=3)

    assert len(clusters) == 3
    total_pop = sum(c.population_count for c in clusters)
    assert total_pop == 1000
    total_pct = sum(c.population_percentage for c in clusters)
    assert abs(total_pct - 100.0) < 0.5

    # Check distinct budget medians across clusters
    b0 = clusters[0].characteristics["economics"]["monthly_budget"]["median"]
    b1 = clusters[1].characteristics["economics"]["monthly_budget"]["median"]
    b2 = clusters[2].characteristics["economics"]["monthly_budget"]["median"]
    assert b0 < b1 < b2


@pytest.mark.asyncio
async def test_deterministic_interpretation_and_evidence_citations():
    """Verify segment profiles are interpreted with grounded descriptions and evidence links."""
    dummy_ds = DatasetSources(
        id="ds_1",
        name="Study Data",
        status="ready",
        row_count=500,
    )
    variables = select_segmentation_variables([dummy_ds])
    clusters = cluster_dataset_populations([dummy_ds], variables, [], desired_clusters=2)

    claim1 = EvidenceClaims(id="clm_1", claim_text="Students are sensitive to pricing above ৳300/mo", category="pricing", status="supported")
    claim2 = EvidenceClaims(id="clm_2", claim_text="Daily study scheduling is fragmented across paper and chat apps", category="behavior", status="supported")

    interpreted = await interpret_market_segments(
        clusters=clusters,
        study_context={"prompt": "AI study planner for university students in Bangladesh", "title": "Study Planner AI"},
        claims=[claim1, claim2],
        llm_service=None,  # Tests deterministic fallback
    )

    assert len(interpreted) == 2
    assert "Students" in interpreted[0].name or "Users" in interpreted[0].name
    assert interpreted[0].population_count > 0
    assert len(interpreted[0].evidence_citations) > 0
    assert interpreted[0].differentiation_summary is not None
