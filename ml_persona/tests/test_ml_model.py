"""Offline model contracts using invented, coherent profile bundles."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from bebshax_persona_ml.data import TrainingRecord
from bebshax_persona_ml.model import (
    BusinessContext,
    ModelConfig,
    PersonaModel,
    PersonaModelError,
    Selection,
)


@pytest.fixture
def training_records() -> list[TrainingRecord]:
    return [
        TrainingRecord(
            record_id="cooking", source="invented", revision="test-1",
            name="Alex Example", age=24, occupation="baker", location="Test City, USA",
            description="Alex Example bakes bread and prepares affordable cooking recipes.",
            goals=["Improve bread recipes and cooking skills."],
            pain_points=["Limited budget for cooking ingredients."],
            behaviors=["Bakes bread daily."],
            documents={"culinary_persona": "Alex Example enjoys bread recipes."},
        ),
        TrainingRecord(
            record_id="electrical", source="invented", revision="test-1",
            name="Morgan Sample", age=48, occupation="electrician", location="Other City, USA",
            description="Morgan Sample repairs electrical circuits and wiring.",
            goals=["Diagnose electrical faults and improve wiring safety."],
            pain_points=["Expensive circuit testing equipment."],
            behaviors=["Tests electrical circuits daily."],
            documents={"hobbies_and_interests": "Morgan Sample repairs circuits."},
        ),
    ]


@pytest.mark.parametrize("description, expected_id", [
    ("Affordable bread cooking recipes and ingredients", "cooking"),
    ("Electrical circuit wiring safety equipment", "electrical"),
])
def test_fitted_model_selects_relevant_complete_bundle(
    training_records: list[TrainingRecord], description: str, expected_id: str,
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(n_topics=2, temperature=0.0001))

    selected = model.generate(BusinessContext(description=description), num_personas=1, seed=7)

    assert len(selected) == 1
    assert isinstance(selected[0], Selection)
    assert selected[0].record == next(
        record for record in training_records if record.record_id == expected_id
    )
    assert 0 < selected[0].score <= 1
    assert 0 <= selected[0].topic < 2
    assert selected[0].model_version == model.version
    assert selected[0].model_dump(mode="json")["record"]["record_id"] == expected_id


def test_fit_rejects_empty_training_records() -> None:
    with pytest.raises(PersonaModelError, match="(?i)candidate|empty"):
        PersonaModel.fit([])


@pytest.fixture
def many_records(training_records: list[TrainingRecord]) -> list[TrainingRecord]:
    return [
        record.model_copy(update={
            "record_id": f"{record.record_id}-{index}",
            "name": f"Fixture Person {group}-{index}",
            "description": record.description.replace(
                record.name, f"Fixture Person {group}-{index}",
            ) + f" Lives in district {index}.",
            "documents": {}, "age": 18 + group * 30 + index,
        }, deep=True)
        for group, record in enumerate(training_records) for index in range(6)
    ]


def test_context_text_preserves_every_input_string_without_truncation() -> None:
    values = {
        "description": "  " + "complete context " * 1100 + "end-description  ",
        "target_audience": "  end-audience  ", "location": "end-location",
        "price_range": "end-price", "product_category": "end-category",
        "features": ["end-feature-one", " " + "feature " * 200 + "end-feature-two"],
        "research": ["research " * 1100 + "end-research"], "role": "end-role",
    }
    text = BusinessContext(**values).text()

    for value in values.values():
        for item in value if isinstance(value, list) else [value]:
            assert item in text


@pytest.mark.parametrize("changes", [
    {"description": "ab"}, {"description": "   "}, {"description": "x" * 20001},
    {"description": 123}, {"description": None}, {"unknown": "forbidden"},
    {"features": [123]}, {"features": ("not-a-list",)}, {"features": [""]},
    {"features": ["x"] * 101}, {"features": ["x" * 2001]},
    {"research": ["x"] * 101}, {"research": ["x" * 10001]},
    {"target_audience": "x" * 4001}, {"location": "x" * 513},
    {"price_range": "x" * 513}, {"product_category": "x" * 513}, {"role": "x" * 513},
    {"min_age": 17}, {"max_age": 96}, {"min_age": "20"}, {"min_age": True},
    {"min_age": 50, "max_age": 30},
])
def test_context_rejects_invalid_or_unbounded_input(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BusinessContext(**{"description": "valid business", **changes})


@pytest.mark.parametrize("changes", [
    {"seed": -1}, {"seed": 2**32}, {"seed": True}, {"n_topics": 0},
    {"n_topics": 257}, {"max_features": 0}, {"max_features": 100001},
    {"max_iter": 0}, {"max_iter": 5001}, {"lexical_weight": -0.1},
    {"lexical_weight": 1.1}, {"diversity_weight": 1.1},
    {"temperature": 0}, {"temperature": float("nan")},
    {"temperature": float("inf")}, {"device": "cuda"}, {"other": 1},
])
def test_model_config_rejects_bad_parameters(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelConfig(**changes)


def test_auto_device_deliberately_fits_on_cpu(training_records: list[TrainingRecord]) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(device="auto"))

    assert model.config.device == "auto"
    assert model.generate(BusinessContext(description="bread recipes"), 1)


def test_fit_only_keeps_complete_adult_candidates(training_records: list[TrainingRecord]) -> None:
    incomplete = [training_records[0].model_copy(update={
        "record_id": f"missing-{field}", field: value,
    }) for field, value in [
        ("age", None), ("occupation", "  "), ("goals", []), ("pain_points", [" "]),
    ]]

    model = PersonaModel.fit(training_records + incomplete)

    assert model.records == training_records
    with pytest.raises(PersonaModelError, match="(?i)candidate"):
        PersonaModel.fit(incomplete)


@pytest.mark.parametrize("records", [None, [None], [{}]])
def test_fit_rejects_untyped_records(records: object) -> None:
    with pytest.raises(PersonaModelError):
        PersonaModel.fit(records)


def test_fit_reports_empty_vocabulary(training_records: list[TrainingRecord]) -> None:
    empty = training_records[0].model_copy(update={
        "description": "! ?", "occupation": "?", "education": "", "location": "",
        "goals": ["!"], "pain_points": ["?"], "behaviors": [], "documents": {},
    })

    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        PersonaModel.fit([empty])


def test_generate_reports_context_with_no_known_vocabulary(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records)

    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        model.generate(BusinessContext(description="zzzzunknown qqqqunknown"), 1)


@pytest.mark.parametrize("count", [0, -1, 51, True, 1.5, "2"])
def test_generate_rejects_bad_count(training_records: list[TrainingRecord], count: object) -> None:
    model = PersonaModel.fit(training_records)

    with pytest.raises(PersonaModelError, match="(?i)count|num_personas"):
        model.generate(BusinessContext(description="bread recipes"), count)


@pytest.mark.parametrize("arguments", [
    {"seed": -1}, {"seed": True}, {"seed": "42"}, {"seed": 2**32},
    {"exclude_ids": ["cooking"]}, {"exclude_names": {123}},
])
def test_generate_rejects_untyped_sampling_inputs(
    training_records: list[TrainingRecord], arguments: dict[str, object],
) -> None:
    model = PersonaModel.fit(training_records)

    with pytest.raises(PersonaModelError):
        model.generate(BusinessContext(description="bread recipes"), 1, **arguments)


def test_age_bounds_and_exclusions_are_hard_constraints(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records)
    context = BusinessContext(description="bread recipes", min_age=48, max_age=48)

    assert model.generate(context, 1)[0].record.age == 48
    assert model.generate(
        BusinessContext(description="bread recipes"), 1, exclude_names={"  ALEX   EXAMPLE "},
    )[0].record.record_id == "electrical"
    assert model.generate(
        BusinessContext(description="bread recipes"), 1, exclude_ids={"cooking"},
    )[0].record.record_id == "electrical"
    with pytest.raises(PersonaModelError, match="(?i)insufficient|candidate"):
        model.generate(context, 2)
    with pytest.raises(PersonaModelError, match="(?i)insufficient|candidate"):
        model.generate(context, 1, exclude_ids={"electrical"})


def test_duplicate_names_record_ids_and_personas_are_not_renamed_or_repeated(
    training_records: list[TrainingRecord],
) -> None:
    original = training_records[0]
    aliases = [
        original.model_copy(update={"record_id": "same-name", "name": "  ALEX  EXAMPLE ",
                                    "description": "Another cooking description."}),
        original.model_copy(update={"record_id": "same-persona", "name": "Other Fixture"}),
        original.model_copy(update={"name": "New Fixture", "description": "Another profile."}),
    ]
    model = PersonaModel.fit(training_records + aliases)

    selected = model.generate(BusinessContext(description="bread recipes"), 2)

    assert {item.record.record_id for item in selected} == {"cooking", "electrical"}
    assert {item.record.name for item in selected} == {"Alex Example", "Morgan Sample"}
    with pytest.raises(PersonaModelError, match="(?i)insufficient|candidate"):
        model.generate(BusinessContext(description="bread recipes"), 3)


def test_seeded_sampling_is_reproducible_and_varies_across_seeds(
    many_records: list[TrainingRecord],
) -> None:
    config = ModelConfig(n_topics=2, temperature=0.5)
    model = PersonaModel.fit(many_records, config)
    context = BusinessContext(description="bread recipes electrical circuits")

    assert model.generate(context, 5, seed=7) == model.generate(context, 5, seed=7)
    assert model.generate(context, 5) == model.generate(context, 5, seed=config.seed)
    assert model.generate(context, 5, seed=7) == PersonaModel.fit(many_records, config).generate(
        context, 5, seed=7,
    )
    orders = {tuple(item.record.record_id for item in model.generate(context, 5, seed=seed))
              for seed in range(8)}
    assert len(orders) > 1
    assert all(len(set(order)) == 5 for order in orders)


def test_diversity_penalty_selects_complementary_profiles(
    many_records: list[TrainingRecord],
) -> None:
    context = BusinessContext(description="bread cooking recipes ingredients")
    plain = PersonaModel.fit(many_records, ModelConfig(
        n_topics=2, lexical_weight=1, diversity_weight=0, temperature=0.000001,
    ))
    diverse = PersonaModel.fit(many_records, ModelConfig(
        n_topics=2, lexical_weight=1, diversity_weight=1, temperature=0.000001,
    ))

    assert len({item.record.occupation for item in plain.generate(context, 2)}) == 1
    assert len({item.record.occupation for item in diverse.generate(context, 2)}) == 2


def test_location_request_warns_and_never_rewrites_origin(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records)

    selected = model.generate(BusinessContext(description="bread recipes", location="Bangladesh"), 1)

    assert selected[0].record.location == "Test City, USA"
    assert any("location" in warning.lower() and "Bangladesh" in warning
               for warning in selected[0].warnings)


def test_selection_mutation_does_not_change_training_bundles(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records)
    context = BusinessContext(description="bread recipes")
    expected = model.generate(context, 1)
    mutated = model.generate(context, 1)
    mutated[0].record.goals.append("caller mutation")

    assert model.generate(context, 1) == expected
    assert training_records[0].goals == expected[0].record.goals


def test_full_corpus_and_configuration_change_fingerprint_and_learned_output(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records)
    changed = [record.model_copy(update={
        "description": "Gardening flowers and growing vegetable plants.",
        "occupation": "gardener", "goals": ["Grow vegetables and flowers."],
        "pain_points": ["Expensive garden seeds."], "behaviors": [], "documents": {},
    }) for record in training_records]
    changed_model = PersonaModel.fit(changed)
    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        model.generate(BusinessContext(description="gardening vegetables flowers"), 1)
    assert changed_model.generate(BusinessContext(description="gardening vegetables flowers"), 1)
    assert model.version != changed_model.version
    assert model.version != PersonaModel.fit(training_records, ModelConfig(seed=17)).version
    assert model.version != PersonaModel.fit(training_records + [training_records[0].model_copy(
        update={"record_id": "incomplete", "age": None},
    )]).version


@pytest.mark.parametrize("marker", ["Alex Example", "Alex", "sensitivecultural", "sensitivesex",
                                      "sensitivereligion", "sensitiverace"])
def test_vector_text_excludes_names_and_protected_fields_even_when_copied_to_constraints(
    training_records: list[TrainingRecord], marker: str,
) -> None:
    record = training_records[0].model_copy(update={
        "documents": {"cultural_background": "sensitivecultural", "sex": "sensitivesex",
                      "religion": "sensitivereligion", "race": "sensitiverace"},
        "pain_points": [*training_records[0].pain_points, "sensitivecultural"],
    })
    model = PersonaModel.fit([record, training_records[1]])

    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        model.generate(BusinessContext(description=marker), 1)
    assert model.records[0].documents == record.documents


@pytest.fixture
def artifact(tmp_path: Path, training_records: list[TrainingRecord]) -> Path:
    directory = tmp_path / "model"
    PersonaModel.fit(training_records).save(directory)
    return directory


def _reseal_file(directory: Path, name: str) -> None:
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["files"][name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def test_artifact_round_trip_exactly_reproduces_scores_and_seeded_selections(
    tmp_path: Path, many_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(many_records, ModelConfig(n_topics=2, device="auto", seed=9))
    directory = tmp_path / "nested" / "artifact"
    context = BusinessContext(description="bread recipes electrical circuits", location="Bangladesh")

    model.save(directory)
    restored = PersonaModel.load(directory)

    assert restored.version == model.version
    assert restored.config == model.config
    assert restored.records == model.records
    for seed in [0, 7, 42]:
        assert restored.generate(context, 5, seed=seed) == model.generate(context, 5, seed=seed)
    assert {file.name for file in directory.iterdir()} == {
        "config.json", "vocabulary.json", "records.json", "metadata.json", "parameters.npz",
    }
    with np.load(directory / "parameters.npz", allow_pickle=False) as arrays:
        assert all(not arrays[name].dtype.hasobject for name in arrays.files)


def test_artifact_contains_only_complete_training_candidates(
    tmp_path: Path, training_records: list[TrainingRecord],
) -> None:
    incomplete = training_records[0].model_copy(update={"record_id": "not-a-candidate", "age": None})
    model = PersonaModel.fit(training_records + [incomplete])
    model.save(tmp_path / "trained")

    stored = json.loads((tmp_path / "trained" / "records.json").read_text(encoding="utf-8"))

    assert [row["record_id"] for row in stored] == [row.record_id for row in training_records]
    assert stored[0]["description"] == training_records[0].description
    assert PersonaModel.load(tmp_path / "trained").version == model.version


@pytest.mark.parametrize("name", [
    "metadata.json", "config.json", "vocabulary.json", "records.json", "parameters.npz",
])
def test_load_rejects_missing_artifact_file(artifact: Path, name: str) -> None:
    (artifact / name).unlink()

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


def test_load_rejects_nonexistent_artifact(tmp_path: Path) -> None:
    with pytest.raises(PersonaModelError):
        PersonaModel.load(tmp_path / "missing")


@pytest.mark.parametrize("name", ["config.json", "vocabulary.json", "records.json", "parameters.npz"])
def test_load_checks_every_payload_hash(artifact: Path, name: str) -> None:
    with (artifact / name).open("ab") as stream:
        stream.write(b" ")

    with pytest.raises(PersonaModelError, match="(?i)hash|checksum"):
        PersonaModel.load(artifact)


@pytest.mark.parametrize("changes", [
    {"schema_version": 999}, {"schema_version": True}, {"algorithm": "arbitrary.import"},
    {"model_version": "0" * 64}, {"corpus_fingerprint": "0" * 64},
    {"runtime": {"sklearn": "0.0.0"}}, {"n_records": 999999999},
    {"n_features": 0}, {"n_topics": 999999999}, {"nnz": -1},
    {"files": {"../../outside.json": "0" * 64}}, {"unexpected": "forbidden"},
])
def test_load_rejects_versions_dimensions_and_untrusted_metadata(
    artifact: Path, changes: dict[str, object],
) -> None:
    metadata = json.loads((artifact / "metadata.json").read_text(encoding="utf-8"))
    (artifact / "metadata.json").write_text(json.dumps({**metadata, **changes}), encoding="utf-8")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


@pytest.mark.parametrize("name", ["metadata.json", "config.json", "vocabulary.json", "records.json"])
def test_load_rejects_invalid_json_even_with_updated_checksum(artifact: Path, name: str) -> None:
    (artifact / name).write_bytes(b"not-json")
    if name != "metadata.json":
        _reseal_file(artifact, name)

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


@pytest.mark.parametrize("replacement", [[], {"word": 0, "other": 0}, {"word": True}])
def test_load_validates_vocabulary_structure(artifact: Path, replacement: object) -> None:
    (artifact / "vocabulary.json").write_text(json.dumps(replacement), encoding="utf-8")
    _reseal_file(artifact, "vocabulary.json")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


def test_load_rejects_configuration_change_after_checksum_update(artifact: Path) -> None:
    config = json.loads((artifact / "config.json").read_text(encoding="utf-8"))
    (artifact / "config.json").write_text(json.dumps({**config, "seed": 101}), encoding="utf-8")
    _reseal_file(artifact, "config.json")

    with pytest.raises(PersonaModelError, match="(?i)version|fingerprint"):
        PersonaModel.load(artifact)


@pytest.mark.parametrize("array_name, corruption", [
    ("idf", "negative"), ("idf", "nan"), ("components", "negative"),
    ("components", "infinity"), ("components", "shape"), ("components", "dtype"),
    ("components", "object"), ("topics", "negative"), ("topics", "nan"),
    ("lexical_data", "negative"), ("lexical_data", "nan"),
    ("lexical_indices", "negative"), ("lexical_indices", "bounds"),
    ("lexical_indptr", "negative"), ("lexical_indptr", "bounds"),
])
def test_load_validates_numeric_payload_beyond_checksums(
    artifact: Path, array_name: str, corruption: str,
) -> None:
    with np.load(artifact / "parameters.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    if corruption == "shape":
        arrays[array_name] = arrays[array_name][:, :1]
    elif corruption == "dtype":
        arrays[array_name] = arrays[array_name].astype(np.float32)
    elif corruption == "object":
        arrays[array_name] = arrays[array_name].astype(object)
    else:
        arrays[array_name].flat[0] = {
            "negative": -1, "nan": np.nan, "infinity": np.inf, "bounds": 999999999,
        }[corruption]
    np.savez(artifact / "parameters.npz", **arrays)
    _reseal_file(artifact, "parameters.npz")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


def test_load_rejects_archive_paths_and_missing_arrays(artifact: Path) -> None:
    with zipfile.ZipFile(artifact / "parameters.npz", "w") as archive:
        archive.writestr("../../components.npy", b"untrusted")
    _reseal_file(artifact, "parameters.npz")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


def test_load_rejects_oversized_array_header_without_allocating_it(artifact: Path) -> None:
    with np.load(artifact / "parameters.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    buffer = io.BytesIO()
    np.lib.format.write_array_header_1_0(buffer, {
        "descr": "<f8", "fortran_order": False, "shape": (2**40,),
    })
    with zipfile.ZipFile(artifact / "parameters.npz", "w") as archive:
        for name, array in arrays.items():
            payload = io.BytesIO()
            np.save(payload, array, allow_pickle=False)
            archive.writestr(name + ".npy", buffer.getvalue() if name == "idf" else payload.getvalue())
    _reseal_file(artifact, "parameters.npz")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(artifact)


def test_load_bounds_artifact_size_before_reading_payload(artifact: Path) -> None:
    with (artifact / "parameters.npz").open("wb") as stream:
        stream.truncate(1024**3)

    with pytest.raises(PersonaModelError, match="(?i)size|large|limit"):
        PersonaModel.load(artifact)


def test_save_reports_invalid_destination(training_records: list[TrainingRecord], tmp_path: Path) -> None:
    destination = tmp_path / "not-a-directory"
    destination.write_text("existing file", encoding="utf-8")

    with pytest.raises(PersonaModelError):
        PersonaModel.fit(training_records).save(destination)
    assert destination.read_text(encoding="utf-8") == "existing file"


def test_explicit_source_name_is_removed_even_when_name_field_is_absent(
    training_records: list[TrainingRecord],
) -> None:
    record = training_records[0].model_copy(update={
        "name": None, "description": "Alex Example is a baker who cooks bread recipes.",
    })
    model = PersonaModel.fit([record, training_records[1]])

    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        model.generate(BusinessContext(description="Alex Example"), 1)
    assert model.records[0].description == record.description


def test_cultural_sentences_copied_to_pain_points_do_not_enter_features(
    training_records: list[TrainingRecord],
) -> None:
    record = training_records[0].model_copy(update={
        "documents": {"cultural_background": "sensitivecultural. Needs sensitivecustom."},
        "pain_points": [*training_records[0].pain_points, "Needs sensitivecustom."],
    })
    model = PersonaModel.fit([record, training_records[1]])

    with pytest.raises(PersonaModelError, match="(?i)vocabulary"):
        model.generate(BusinessContext(description="sensitivecustom"), 1)
    assert model.records[0].pain_points == record.pain_points


def test_generate_rejects_untyped_context_and_config(training_records: list[TrainingRecord]) -> None:
    with pytest.raises(PersonaModelError, match="config"):
        PersonaModel.fit(training_records, {})
    with pytest.raises(PersonaModelError, match="context"):
        PersonaModel.fit(training_records).generate({"description": "bread recipes"}, 1)


def test_two_thousand_profiles_support_maximum_batch_on_cpu(
    training_records: list[TrainingRecord],
) -> None:
    records = [record.model_copy(update={
        "record_id": f"scale-{group}-{index}", "name": f"Invented Worker {group}-{index}",
        "description": f"Invented Worker {group}-{index} practices {record.occupation} skills.",
        "documents": {},
    }) for group, record in enumerate(training_records) for index in range(1000)]
    model = PersonaModel.fit(records, ModelConfig(n_topics=2, max_features=64))

    selected = model.generate(BusinessContext(description="bread recipes electrical circuits"), 50)

    assert len(model.records) == 2000
    assert len(selected) == len({item.record.record_id for item in selected}) == 50
    assert len({item.record.name for item in selected}) == 50
    assert all(item.record in records for item in selected)


def test_one_candidate_round_trip_and_unknown_origin_warning(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    model = PersonaModel.fit([training_records[0].model_copy(update={"location": ""})])
    context = BusinessContext(description="bread recipes", location="Bangladesh", min_age=18)
    model.save(tmp_path / "single")

    selected = PersonaModel.load(tmp_path / "single").generate(context, 1)

    assert selected == model.generate(context, 1)
    assert selected[0].record.location == ""
    assert any("location" in warning.lower() for warning in selected[0].warnings)