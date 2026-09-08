"""Tests for the Market Segmentation Engine: readiness, variable selection,
quantile clustering over REAL rows, distribution formulas, evidence matching and
LLM-only interpretation. Nothing here may pass on invented populations.
"""

import json

import pytest

from bebshax.db.models import DatasetSources, EvidenceClaims
from bebshax.segmentation.clusterer import (
    SEGMENTATION_REQUIRES_DATA,
    _compute_categorical_stats,
    _compute_numeric_stats,
    cluster_dataset_populations,
    load_dataset_rows,
)
from bebshax.segmentation.interpreter import (
    SEGMENT_INTERPRETATION_FAILED,
    _match_evidence_to_cluster,
    interpret_market_segments,
)
from bebshax.segmentation.pre_check import check_segmentation_readiness
from bebshax.segmentation.variable_selector import select_segmentation_variables
from bebshax.utils.explicit_failures import InsufficientInput, LLMUnavailable, UnusableModelOutput


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


def _survey_dataset(tmp_path, rows: list[dict], ds_id: str = "ds_1") -> DatasetSources:
    path = tmp_path / f"{ds_id}.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return DatasetSources(
        id=ds_id,
        name="Empirical Budget Survey",
        status="ready",
        row_count=len(rows),
        file_path=str(path),
        schema_metadata={
            "columns": [
                {"name": "respondent_id", "type": "text", "missing_percentage": 0, "unique_count": len(rows)},
                {"name": "monthly_budget", "type": "numeric", "missing_percentage": 0, "unique_count": 40},
                {"name": "age", "type": "numeric", "missing_percentage": 0, "unique_count": 12},
                {"name": "device", "type": "categorical", "missing_percentage": 0, "unique_count": 2},
            ]
        },
        statistics={"numeric": {"monthly_budget": {"min": 200, "median": 700, "max": 1400}, "age": {"min": 18, "median": 23, "max": 40}}},
    )


def _rows(n: int = 120) -> list[dict]:
    # Budget rises with the index; age and device correlate with budget so the
    # per-band profiles must differ if they are really computed from the rows.
    return [
        {
            "respondent_id": f"r{i}",
            "monthly_budget": 200 + i * 10,
            "age": 18 + (i // 6),
            "device": "phone" if i < n // 2 else "laptop",
        }
        for i in range(n)
    ]


def test_segmentation_readiness_states(tmp_path):
    """Only observed records can be segmented; claims alone or nothing -> cannot run."""
    no_data = check_segmentation_readiness("study_1", [], [])
    assert no_data.status == "no_data" and no_data.can_run is False
    assert "does not invent segments" in no_data.guidance_message

    claim = EvidenceClaims(id="clm_1", claim_text="Students want cheap tools", status="supported")
    claims_only = check_segmentation_readiness("study_1", [], [claim] * 5)
    assert claims_only.status == "no_data" and claims_only.can_run is False

    tiny = _survey_dataset(tmp_path, _rows(8), ds_id="ds_tiny")
    small = check_segmentation_readiness("study_1", [tiny], [claim])
    assert small.status == "insufficient_records" and small.can_run is False
    assert "at least 20" in small.guidance_message

    ready = check_segmentation_readiness("study_1", [_survey_dataset(tmp_path, _rows())], [claim])
    assert ready.status == "ready" and ready.can_run is True
    assert ready.total_records == 120
    assert ready.usable_variables_count == 3  # id column excluded


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


def test_cluster_populations_are_quantiles_of_the_actual_rows(tmp_path):
    ds = _survey_dataset(tmp_path, _rows())
    variables = select_segmentation_variables([ds])
    clusters = cluster_dataset_populations([ds], variables, [], desired_clusters=3)

    assert len(clusters) == 3
    assert sum(c.population_count for c in clusters) == 120
    assert abs(sum(c.population_percentage for c in clusters) - 100.0) < 0.5
    assert all(c.characteristics["partition_method"] == "quantile_bands" for c in clusters)
    assert all(c.characteristics["partition_variable"] == "monthly_budget" for c in clusters)

    # Medians rise band by band and are the real values from the rows.
    medians = [c.variable_distributions["monthly_budget"]["median"] for c in clusters]
    assert medians[0] < medians[1] < medians[2]
    assert 200 <= medians[0] <= 600 and 1000 <= medians[2] <= 1400
    # Co-variables are profiled per band: the low-budget band is younger and phone-based.
    low, high = clusters[0], clusters[-1]
    assert low.variable_distributions["age"]["median"] < high.variable_distributions["age"]["median"]
    assert low.variable_distributions["device"]["top_categories"][0]["category"] == "phone"
    assert high.variable_distributions["device"]["top_categories"][0]["category"] == "laptop"
    # No assumed demographics, currency or needs anywhere.
    dumped = json.dumps([c.model_dump() for c in clusters])
    for invented in ("age_range", "BDT", "\u09f3", "technology_familiarity", "Affordable structured plans", "Price-Sensitive"):
        assert invented not in dumped


def test_cluster_without_rows_fails_explicitly():
    ds = DatasetSources(id="ds_norows", name="Study Data", status="ready", row_count=500)
    with pytest.raises(InsufficientInput) as info:
        cluster_dataset_populations([ds], select_segmentation_variables([ds]), [], desired_clusters=2)
    assert info.value.error_code == SEGMENTATION_REQUIRES_DATA
    assert info.value.status_code == 400
    assert load_dataset_rows(ds) == []


def test_explicit_dataset_segments_carry_only_observed_constraints():
    ds = DatasetSources(
        id="ds_seg",
        name="Grouped",
        status="ready",
        row_count=300,
        segments=[
            {"name": "Commuters", "population_count": 200, "population_percentage": 66.7, "constraints": {"mode": "bus", "rule_description": "mode == bus"}},
            {"name": "Cyclists", "population_count": 100, "population_percentage": 33.3, "constraints": {"mode": "bike"}},
        ],
    )
    clusters = cluster_dataset_populations([ds], [], [])
    assert [c.population_count for c in clusters] == [200, 100]
    assert clusters[0].characteristics["observed_constraints"] == {"mode": "bus", "rule_description": "mode == bus"}
    assert clusters[0].characteristics["partition_method"] == "categorical_grouping"
    assert "demographics" not in clusters[0].characteristics and "economics" not in clusters[0].characteristics


class _StubLLM:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list = []

    async def complete(self, request):
        self.requests.append(request)
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[0]

        class _R:
            provider = "fake"
            model = "stub"

        r = _R()
        r.text = text
        return r


def _clusters(tmp_path):
    ds = _survey_dataset(tmp_path, _rows())
    return cluster_dataset_populations([ds], select_segmentation_variables([ds]), [], desired_clusters=2)


@pytest.mark.asyncio
async def test_interpretation_is_model_written_from_the_observed_clusters(tmp_path):
    clusters = _clusters(tmp_path)
    claim_budget = EvidenceClaims(id="clm_1", claim_text="Respondents cap their monthly budget for phone tools", category="pricing", status="supported")
    claim_unrelated = EvidenceClaims(id="clm_2", claim_text="Harbour freight tonnage grew last quarter", category="market", status="inference")
    reply = json.dumps(
        {
            "segments": [
                {"cluster_label": "cluster_0", "name": "Phone-first savers (200–790)", "description": "Median budget 490; 100% phone.", "differentiation_summary": "Lowest budgets, youngest."},
                {"cluster_label": "cluster_1", "name": "Laptop spenders (800–1390)", "description": "Median budget 1090; laptop users.", "differentiation_summary": "Highest budgets."},
            ]
        }
    )
    stub = _StubLLM(reply)
    interpreted = await interpret_market_segments(
        clusters=clusters,
        study_context={"prompt": "Budget planner for commuters", "title": "Planner"},
        claims=[claim_budget, claim_unrelated],
        llm_service=stub,
    )
    assert [s.name for s in interpreted] == ["Phone-first savers (200–790)", "Laptop spenders (800–1390)"]
    assert interpreted[0].characteristics["interpretation_source"] == "llm"
    assert interpreted[0].characteristics["served_by"] == "fake/stub"
    # Evidence is linked by shared observed vocabulary — the unrelated claim is not padded in.
    cited = {c["claim_id"] for c in interpreted[0].evidence_citations}
    assert cited == {"clm_1"}
    # The cluster statistics travel as untrusted data.
    assert "CLUSTER_ANALYSIS" in stub.requests[0].messages[-1].content
    assert "quantile_bands" in stub.requests[0].messages[-1].content


def test_evidence_matching_returns_empty_when_nothing_is_related(tmp_path):
    clusters = _clusters(tmp_path)
    unrelated = EvidenceClaims(id="clm_x", claim_text="Harbour freight tonnage grew last quarter", category="market")
    assert _match_evidence_to_cluster(clusters[0], [unrelated]) == []


@pytest.mark.asyncio
async def test_interpretation_without_llm_fails_explicitly(tmp_path):
    with pytest.raises(LLMUnavailable):
        await interpret_market_segments(_clusters(tmp_path), {"prompt": "x"}, [], llm_service=None)


@pytest.mark.asyncio
async def test_interpretation_unusable_reply_retries_once_then_fails(tmp_path):
    stub = _StubLLM(json.dumps({"segments": [{"cluster_label": "cluster_0", "name": "only one", "description": "d"}]}))
    with pytest.raises(UnusableModelOutput) as info:
        await interpret_market_segments(_clusters(tmp_path), {"prompt": "x"}, [], llm_service=stub)
    assert len(stub.requests) == 2  # a reply missing a cluster is retried, then refused
    assert info.value.error_code == SEGMENT_INTERPRETATION_FAILED
