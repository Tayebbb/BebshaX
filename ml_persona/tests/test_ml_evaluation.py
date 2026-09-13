"""Held-out retrieval and generation diagnostics on invented offline profiles."""

import json
from pathlib import Path

import numpy as np
import pytest

from bebshax_persona_ml.data import TrainingRecord
from bebshax_persona_ml.evaluation import evaluate_model
from bebshax_persona_ml.model import BusinessContext, ModelConfig, PersonaModel, PersonaModelError, Selection


@pytest.fixture
def evaluation_case() -> tuple[PersonaModel, list[TrainingRecord]]:
    domains = ["bread recipes cooking", "electrical wiring circuits", "flowers garden seeds",
               "music piano concerts", "pottery clay ceramics", "photography cameras portraits"]
    # Training and held-out query views share the "enjoys ... at home" phrasing so
    # every query has several lexically relevant candidates; relevance (score > 0)
    # must not hinge on NMF rounding, which differs between BLAS builds.
    training = [TrainingRecord(
        record_id=f"training-{index}", source="invented", revision="one", name=f"Trainer {index}",
        age=20 + 10 * index, occupation=f"worker {index}",
        description=f"Training profile practices {domain} professionally.",
        goals=[f"Improve {domain}."], pain_points=[f"Limited {domain} supplies."],
        documents={"skills_and_expertise": domain, "culinary_persona": f"Enjoys {domain} at home."},
    ) for index, domain in enumerate(domains)]
    heldout = [TrainingRecord(
        record_id=f"heldout-{index}", source="invented", revision="two", name=f"Heldout {index}",
        age=20 + 10 * index, occupation=f"worker {index}",
        description=f"Heldout {index} has a separate identity for testing {domain}.",
        goals=[f"Practice {domain}."], pain_points=["Limited supplies."],
        documents={"culinary_persona": f"Heldout {index} enjoys {domain} at home.",
                   "professional_persona": f"Heldout {index} teaches {domain} at work."},
    ) for index, domain in enumerate(domains)]
    return PersonaModel.fit(training, ModelConfig(n_topics=6, temperature=0.0001)), heldout


def test_known_perfect_cross_view_retrieval_beats_random_and_frequency(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case

    report = evaluate_model(model, heldout, seed=42)

    assert report["schema_version"] == 1
    assert report["model_version"] == model.version
    assert report["seed"] == 42
    assert "proxy" in report["interpretation"].lower()
    assert "not" in report["interpretation"].lower()
    retrieval = report["retrieval"]
    assert retrieval["rank_scope"] == "evaluation_records_only"
    assert retrieval["candidate_count"] == retrieval["query_count"] == len(heldout)
    for method in ["model", "lexical_tfidf"]:
        assert retrieval[method] == {"mrr": 1.0, "recall@1": 1.0, "recall@5": 1.0, "recall@10": 1.0}
    assert retrieval["random"]["mrr"] == pytest.approx(sum(1 / rank for rank in range(1, 7)) / 6)
    assert retrieval["random"]["recall@1"] == pytest.approx(1 / 6)
    assert retrieval["random"]["recall@5"] == pytest.approx(5 / 6)
    assert retrieval["popular_occupation"]["mrr"] < 1
    json.dumps(report, allow_nan=False)


def test_lexical_evaluation_never_calls_nmf_and_has_no_topic_coverage(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference, heldout = evaluation_case

    def forbidden_nmf(*args: object, **kwargs: object) -> None:
        pytest.fail("Lexical evaluation must not construct or call NMF")

    monkeypatch.setattr("bebshax_persona_ml.model.NMF", forbidden_nmf)
    lexical = PersonaModel.fit(reference.records, ModelConfig(strategy="lexical", lexical_weight=1.0))

    report = evaluate_model(lexical, heldout)

    assert report["retrieval"]["model"] == report["retrieval"]["lexical_tfidf"]
    assert report["retrieval"]["model"]["mrr"] == 1.0
    assert report["generation"]["coverage"]["topic_fraction"] is None
    assert report["generation"]["coverage"]["topic_counts"] == {}
    assert report["generation"]["successful_batches"] == len(heldout)
    assert report["generation"]["sample_count"] == 5 * len(heldout)
    json.dumps(report, allow_nan=False)


def test_evaluation_does_not_fit_or_modify_the_training_index(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], tmp_path: Path,
) -> None:
    model, heldout = evaluation_case
    context = BusinessContext(description="Enjoys bread recipes cooking at home.")
    before = model.generate(context, 3, seed=19)
    model.save(tmp_path / "before")

    evaluate_model(model, heldout, seed=19)
    model.save(tmp_path / "after")

    assert model.generate(context, 3, seed=19) == before
    for name in ["config.json", "vocabulary.json", "records.json"]:
        assert (tmp_path / "before" / name).read_bytes() == (tmp_path / "after" / name).read_bytes()
    with np.load(tmp_path / "before" / "parameters.npz", allow_pickle=False) as before_arrays:
        with np.load(tmp_path / "after" / "parameters.npz", allow_pickle=False) as after_arrays:
            for name in before_arrays.files:
                np.testing.assert_array_equal(before_arrays[name], after_arrays[name])
    assert {record.record_id for record in model.records}.isdisjoint(record.record_id for record in heldout)


@pytest.mark.parametrize("records", [[], None, [None], [{}]])
def test_evaluation_rejects_missing_or_untyped_records(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], records: object,
) -> None:
    with pytest.raises(PersonaModelError):
        evaluate_model(evaluation_case[0], records)


def test_evaluation_rejects_training_identity_overlap(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case

    with pytest.raises(PersonaModelError, match="(?i)held.?out|overlap|disjoint"):
        evaluate_model(model, heldout + [model.records[0]])


@pytest.mark.parametrize("field", ["record_id", "name", "description"])
def test_evaluation_rejects_overlap_under_any_identity_key(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], field: str,
) -> None:
    model, heldout = evaluation_case
    overlap = heldout[0].model_copy(update={field: getattr(model.records[0], field)})

    with pytest.raises(PersonaModelError, match="(?i)held.?out|overlap|disjoint"):
        evaluate_model(model, [overlap, *heldout[1:]])


def test_evaluation_rejects_duplicate_evaluation_identities(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case

    with pytest.raises(PersonaModelError, match="(?i)duplicate|unique"):
        evaluate_model(model, heldout + [heldout[0]])


@pytest.mark.parametrize("seed", [-1, True, "42", 2**32])
def test_evaluation_rejects_invalid_seed(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], seed: object,
) -> None:
    with pytest.raises(PersonaModelError):
        evaluate_model(evaluation_case[0], evaluation_case[1], seed=seed)


def test_missing_and_out_of_vocabulary_views_remain_in_metric_denominator(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case
    records = [
        heldout[0].model_copy(update={"documents": {"professional_persona": "bread recipes"}}),
        heldout[1].model_copy(update={"documents": {"culinary_persona": "electrical circuits"}}),
        heldout[2].model_copy(update={"documents": {
            "culinary_persona": "zzzzunknown", "professional_persona": "qqqqunknown",
        }}),
        *heldout[3:],
    ]

    retrieval = evaluate_model(model, records)["retrieval"]

    assert retrieval["query_count"] == retrieval["candidate_count"] == 6
    assert retrieval["valid_query_count"] == 3
    assert retrieval["invalid_view_counts"] == {"missing_query": 1, "missing_profile": 1,
                                               "oov_query": 1, "oov_profile": 1}
    assert retrieval["model"]["mrr"] == pytest.approx(0.5)
    assert retrieval["model"]["recall@10"] == pytest.approx(0.5)
    assert retrieval["lexical_tfidf"]["mrr"] == pytest.approx(0.5)


def test_names_are_removed_from_both_views_before_retrieval(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case
    names = ["Bread Recipes", "Electrical Circuits", "Flowers Garden", "Music Piano", "Pottery Clay", "Photography Cameras"]
    only_names = [record.model_copy(update={
        "name": name, "description": f"Unrelated heldout identity {index}.",
        "documents": {"culinary_persona": name, "professional_persona": name},
    }) for index, (record, name) in enumerate(zip(heldout, names, strict=True))]

    report = evaluate_model(model, only_names)

    assert report["retrieval"]["valid_query_count"] == 0
    assert report["retrieval"]["invalid_view_counts"]["missing_query"] == 6
    assert report["retrieval"]["invalid_view_counts"]["missing_profile"] == 6
    assert report["retrieval"]["model"]["mrr"] == 0
    assert report["retrieval"]["lexical_tfidf"]["mrr"] == 0
    assert report["generation"]["sample_count"] == 0
    assert report["generation"]["age_distribution"]["js_divergence"] is None
    assert report["generation"]["diversity"]["mean_pairwise_cosine_distance"] is None


def test_eval_excludes_shared_summary_and_derived_fields_from_candidate_view(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case
    contaminated = [record.model_copy(update={
        "documents": {"culinary_persona": record.documents["culinary_persona"],
                      "persona": record.documents["culinary_persona"],
                      "cultural_background": record.documents["culinary_persona"]},
        "description": record.description + record.documents["culinary_persona"],
        "goals": [record.documents["culinary_persona"]],
        "behaviors": [record.documents["culinary_persona"]],
    }) for record in heldout]

    report = evaluate_model(model, contaminated)

    assert report["retrieval"]["valid_query_count"] == 0
    assert report["retrieval"]["invalid_view_counts"]["missing_profile"] == len(heldout)
    assert report["retrieval"]["model"]["mrr"] == 0


def test_generation_metrics_are_bounded_real_sample_statistics(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case

    report = evaluate_model(model, heldout, seed=9)
    generation = report["generation"]

    assert generation["requested_batches"] == generation["successful_batches"] == 6
    assert generation["failed_batches"] == generation["skipped_queries"] == 0
    assert generation["sample_count"] == 30
    assert generation["structural"] == {
        "incomplete_count": 0, "underage_count": 0, "duplicate_id_count": 0,
        "duplicate_name_count": 0, "duplicate_persona_count": 0,
        "bundle_mismatch_count": 0, "location_rewrite_count": 0,
    }
    assert generation["exact_source_reuse_rate"] == 1
    assert "expected" in generation["reuse_interpretation"].lower()
    age = generation["age_distribution"]
    assert age["reference"] == "heldout_source_records"
    assert 0 <= age["js_divergence"] <= 1
    assert age["generated_unknown"] == age["source_unknown"] == 0
    assert sum(age["generated_counts"]) == generation["sample_count"]
    assert sum(age["source_counts"]) == len(heldout)
    diversity = generation["diversity"]
    assert diversity["space"] == "training_tfidf_cosine"
    assert 0 < diversity["mean_pairwise_cosine_distance"] <= 1
    assert 0 < generation["coverage"]["record_fraction"] <= 1
    assert 0 < generation["coverage"]["occupation_fraction"] <= 1
    assert 0 < generation["coverage"]["topic_fraction"] <= 1
    assert sum(generation["coverage"]["occupation_counts"].values()) == 30
    assert sum(generation["coverage"]["topic_counts"].values()) == 30
    assert all(value >= 0 for value in report["latency_ms"].values())
    assert all(value >= 0 for value in generation["latency_ms"].values())
    assert "accuracy" not in json.dumps(report).lower()
    json.dumps(report, allow_nan=False)


def test_generation_age_js_detects_disjoint_generated_and_source_age_bins(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case
    young_training = [record.model_copy(update={"age": 18}) for record in model.records]
    model = PersonaModel.fit(young_training, ModelConfig(n_topics=6))
    older_heldout = [record.model_copy(update={"age": 90}) for record in heldout]

    age = evaluate_model(model, older_heldout)["generation"]["age_distribution"]

    assert age["js_divergence"] == pytest.approx(1.0)
    assert age["generated_counts"][0] == 30
    assert age["source_counts"][-1] == 6


def test_missing_source_ages_are_counted_not_imputed(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case

    age = evaluate_model(model, [record.model_copy(update={"age": None}) for record in heldout])[
        "generation"
    ]["age_distribution"]

    assert age["source_unknown"] == 6
    assert sum(age["source_counts"]) == 0
    assert age["js_divergence"] is None


def test_metrics_except_latency_are_reproducible(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]],
) -> None:
    model, heldout = evaluation_case
    first, second = evaluate_model(model, heldout, seed=17), evaluate_model(model, heldout, seed=17)
    for report in [first, second]:
        del report["latency_ms"]
        del report["generation"]["latency_ms"]

    assert first == second


def test_generation_metrics_count_real_failures_instead_of_hiding_them(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, heldout = evaluation_case

    def unavailable(*arguments: object, **keywords: object) -> list[Selection]:
        raise PersonaModelError("fixture generation failure")

    monkeypatch.setattr(model, "generate", unavailable)

    report = evaluate_model(model, heldout)

    assert report["generation"]["failed_batches"] == 6
    assert report["generation"]["successful_batches"] == 0
    assert report["generation"]["sample_count"] == 0
    assert report["retrieval"]["model"]["mrr"] == 1


def test_generation_diagnostics_detect_incoherent_mutated_bundle(
    evaluation_case: tuple[PersonaModel, list[TrainingRecord]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, heldout = evaluation_case
    changed = model.records[0].model_copy(update={"age": 17, "location": "Rewritten", "goals": []})
    corrupted = Selection(record=changed, score=0.5, topic=0, model_version=model.version)

    monkeypatch.setattr(model, "generate", lambda *arguments, **keywords: [corrupted, corrupted])
    metrics = evaluate_model(model, heldout)["generation"]

    assert metrics["structural"]["underage_count"] == 12
    assert metrics["structural"]["incomplete_count"] == 12
    assert metrics["structural"]["bundle_mismatch_count"] == 12
    assert metrics["structural"]["location_rewrite_count"] == 12
    assert metrics["structural"]["duplicate_id_count"] == 6
    assert metrics["structural"]["duplicate_name_count"] == 6
    assert metrics["structural"]["duplicate_persona_count"] == 6
    assert metrics["exact_source_reuse_rate"] == 0


def test_cosine_diversity_is_not_name_diversity() -> None:
    training = [TrainingRecord(
        record_id=f"identical-{index}", source="invented", revision="one", name=f"Worker {index}",
        age=30, occupation="baker", description=f"Worker {index} bakes bread.",
        goals=["Bake bread."], pain_points=["Limited bread ingredients."],
    ) for index in range(4)]
    heldout = [TrainingRecord(
        record_id=f"eval-{index}", source="invented", revision="one", name=f"Subject {index}",
        age=30, occupation="baker", description=f"Subject {index} cooks recipes.",
        goals=["Cook recipes."], pain_points=["Limited time."],
        documents={"culinary_persona": "bread", "professional_persona": "bread"},
    ) for index in range(2)]

    report = evaluate_model(PersonaModel.fit(training, ModelConfig(n_topics=1)), heldout)

    assert report["generation"]["diversity"]["mean_pairwise_cosine_distance"] == pytest.approx(0, abs=1e-12)
    assert report["generation"]["structural"]["duplicate_name_count"] == 0