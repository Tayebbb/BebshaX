"""Offline model contracts using invented, coherent profile bundles."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from bebshax_persona_ml.data import TrainingRecord, fingerprint
from bebshax_persona_ml.model import (
    BusinessContext,
    ModelConfig,
    PersonaModel,
    PersonaModelError,
    Selection,
)


@pytest.mark.parametrize("notice", [None, "", "   "])
def test_verified_attribution_requires_license_notice(notice: str | None) -> None:
    from bebshax_persona_ml.provenance import SourceAttribution

    with pytest.raises(ValidationError):
        SourceAttribution(
            source="invented", revision="test-1", creator="Fixture creator",
            source_url="https://example.invalid/source", license="CC-BY-4.0",
            license_reference_url="https://creativecommons.org/licenses/by/4.0/",
            license_notice=notice, modifications=["Test-only normalized synthetic records."],
            metadata_status="verified_ingestion_metadata",
        )


def test_new_artifact_records_tokenizer_contract(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(strategy="lexical", lexical_weight=1.0))
    model.save(tmp_path / "tokenizer")
    metadata = json.loads((tmp_path / "tokenizer/metadata.json").read_text(encoding="utf-8"))

    assert metadata["schema_version"] == 3
    contract = metadata["tokenizer_contract"]
    assert contract["implementation"] == "sklearn.feature_extraction.text.TfidfVectorizer"
    assert contract["parameters"]["token_pattern"] == r"(?u)\b\w\w+\b"
    assert contract["parameters"]["lowercase"] is True
    assert contract["parameters"]["ngram_range"] == [1, 1]
    assert len(contract["stop_words_sha256"]) == 64
    assert contract["truncation"] is False
    assert contract["max_input_tokens"] is None
    restored = PersonaModel.load(tmp_path / "tokenizer", verify_training_code=True)
    context = BusinessContext(description="bread cooking recipes")
    assert restored.generate(context, 1, seed=4) == model.generate(context, 1, seed=4)


@pytest.mark.parametrize("change", ["lowercase", "token_pattern", "stop_words", "unicode", "missing"])
def test_artifact_rejects_changed_tokenizer_contract(
    training_records: list[TrainingRecord], tmp_path: Path, change: str,
) -> None:
    directory = tmp_path / "tokenizer"
    PersonaModel.fit(training_records, ModelConfig(strategy="lexical", lexical_weight=1.0)).save(directory)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    if change == "missing":
        metadata.pop("tokenizer_contract", None)
    elif change == "lowercase":
        metadata["tokenizer_contract"]["parameters"]["lowercase"] = False
    elif change == "token_pattern":
        metadata["tokenizer_contract"]["parameters"]["token_pattern"] = r"\w+"
    elif change == "unicode":
        metadata["tokenizer_contract"]["unicode_version"] = "0.0.0"
    else:
        metadata["tokenizer_contract"]["stop_words_sha256"] = "0" * 64
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersonaModelError, match="(?i)tokenizer"):
        PersonaModel.load(directory)


def test_schema_two_artifact_keeps_original_identity(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(strategy="lexical", lexical_weight=1.0))
    model._schema_version = 2
    model.version = model._revision()
    model.save(tmp_path / "schema-two")
    metadata = json.loads((tmp_path / "schema-two/metadata.json").read_text(encoding="utf-8"))

    assert metadata["schema_version"] == 2
    assert "tokenizer_contract" not in metadata
    restored = PersonaModel.load(tmp_path / "schema-two")
    assert restored.version == model.version
    restored.save(tmp_path / "schema-two-roundtrip")
    assert PersonaModel.load(tmp_path / "schema-two-roundtrip").version == model.version


@pytest.mark.parametrize("tampered", [False, True])
def test_legacy_optional_tokenizer_contract_is_verified(
    training_records: list[TrainingRecord], tmp_path: Path, tampered: bool,
) -> None:
    model = PersonaModel.fit(training_records)
    model._schema_version = 2
    model.version = model._revision()
    model.save(tmp_path / "legacy-tokenizer")
    path = tmp_path / "legacy-tokenizer/metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["tokenizer_contract"] = model._tokenizer_contract
    if tampered:
        metadata["tokenizer_contract"]["parameters"]["lowercase"] = False
    path.write_text(json.dumps(metadata), encoding="utf-8")

    if tampered:
        with pytest.raises(PersonaModelError, match="(?i)tokenizer"):
            PersonaModel.load(path.parent)
    else:
        assert PersonaModel.load(path.parent).version == model.version


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
    context = BusinessContext(description="bread recipes electrical circuits", min_age=48, max_age=48)

    assert model.generate(context, 1)[0].record.age == 48
    assert model.generate(
        BusinessContext(description="bread recipes electrical circuits"), 1, exclude_names={"  ALEX   EXAMPLE "},
    )[0].record.record_id == "electrical"
    assert model.generate(
        BusinessContext(description="bread recipes electrical circuits"), 1, exclude_ids={"cooking"},
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

    selected = model.generate(BusinessContext(description="bread recipes electrical circuits"), 2)

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
    context = BusinessContext(description="bread cooking recipes ingredients electrical")
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


def test_lexical_strategy_never_calls_nmf_during_training_loading_or_serving(
    training_records: list[TrainingRecord], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_nmf(*args: object, **kwargs: object) -> None:
        pytest.fail("A genuine lexical strategy must never construct or call NMF")

    monkeypatch.setattr("bebshax_persona_ml.model.NMF", forbidden_nmf)
    config = ModelConfig(strategy="lexical", lexical_weight=1.0, temperature=0.0001)
    model = PersonaModel.fit(training_records, config)
    context = BusinessContext(description="bread recipes " * 1000 + "ingredients")
    selected = model.generate(context, 1)
    model.save(tmp_path / "lexical")
    restored = PersonaModel.load(tmp_path / "lexical")

    assert selected[0].record == training_records[0]
    assert selected[0].topic is None
    assert 0 < selected[0].score <= 1
    assert restored.config.strategy == "lexical"
    assert restored.generate(context, 1) == selected
    with np.load(tmp_path / "lexical" / "parameters.npz", allow_pickle=False) as arrays:
        assert "components" not in arrays.files
        assert "topics" not in arrays.files


def test_default_strategy_remains_nmf_even_with_full_lexical_weight(
    training_records: list[TrainingRecord],
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(lexical_weight=1.0))

    assert model.config.strategy == "nmf"
    assert model.generate(BusinessContext(description="bread recipes"), 1)[0].topic is not None


def test_legacy_artifact_without_strategy_retains_original_version_and_nmf(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    directory = tmp_path / "legacy"
    PersonaModel.fit(training_records).save(directory)
    configuration = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    configuration.pop("strategy", None)
    (directory / "config.json").write_text(json.dumps(configuration), encoding="utf-8")
    _reseal_file(directory, "config.json")
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    metadata["schema_version"] = 1
    metadata.pop("provenance", None)
    metadata.pop("tokenizer_contract", None)
    original_version = fingerprint({
        "corpus": metadata["corpus_fingerprint"], "config": configuration,
        "algorithm": "tfidf-nmf-mmr-v1",
    })
    metadata["model_version"] = original_version
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    restored = PersonaModel.load(directory)

    assert restored.version == original_version
    assert restored.config.strategy == "nmf"
    assert restored.generate(BusinessContext(description="bread recipes"), 1)[0].topic is not None
    restored.save(tmp_path / "legacy-resaved")
    assert PersonaModel.load(tmp_path / "legacy-resaved").version == original_version


@pytest.mark.parametrize("strategy", ["nmf", "lexical"])
@pytest.mark.parametrize("arguments", [
    {"num_personas": 2},
    {"num_personas": 1, "exclude_ids": {"cooking"}},
    {"num_personas": 1, "exclude_names": {" ALEX  EXAMPLE "}},
])
def test_zero_score_sources_never_fill_a_requested_cohort(
    training_records: list[TrainingRecord], strategy: str, arguments: dict[str, object],
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(strategy=strategy, lexical_weight=1.0))

    with pytest.raises(PersonaModelError, match="(?i)insufficient.*relevan"):
        model.generate(BusinessContext(description="bread recipes"), **arguments)


@pytest.mark.parametrize("strategy", ["nmf", "lexical"])
def test_relevance_cannot_override_hard_age_constraints(
    training_records: list[TrainingRecord], strategy: str,
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(strategy=strategy, lexical_weight=1.0))

    with pytest.raises(PersonaModelError, match="(?i)insufficient.*relevan"):
        model.generate(BusinessContext(description="bread recipes", min_age=48, max_age=48), 1)


@pytest.mark.parametrize("changes", [
    {"strategy": "unknown"}, {"strategy": None},
    {"strategy": "lexical", "lexical_weight": 0.7},
])
def test_strategy_config_rejects_ambiguous_or_invalid_identity(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelConfig(**changes)


def test_lexical_tail_vocabulary_and_complete_source_narratives_are_preserved(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    original = training_records[0].model_copy(update={
        "documents": {"arts_persona": "full unchanged narrative " * 2000 + "tailrelevancemarker"},
    }, deep=True)
    model = PersonaModel.fit([original, training_records[1]], ModelConfig(
        strategy="lexical", lexical_weight=1.0,
    ))
    model.save(tmp_path / "full-text")

    selected = PersonaModel.load(tmp_path / "full-text").generate(BusinessContext(
        description="outofvocabulary " * 1000 + "tailrelevancemarker",
    ), 1)

    assert selected[0].record == original
    assert selected[0].score > 0


@pytest.mark.parametrize("strategy", ["nmf", "lexical"])
def test_manifest_covers_source_records_training_code_and_explicit_unknown_attribution(
    training_records: list[TrainingRecord], tmp_path: Path, strategy: str,
) -> None:
    model = PersonaModel.fit(training_records, ModelConfig(strategy=strategy, lexical_weight=1.0))
    model.save(tmp_path / "provenance")

    provenance = model.provenance
    assert provenance.source_records_sha256 == fingerprint([record.model_dump(mode="json") for record in training_records])
    assert provenance.training_code_sha256 == fingerprint(provenance.training_code)
    assert set(provenance.training_code) >= {
        "model.py", "data.py", "pipeline.py", "evaluation.py", "cli.py", "provenance.py",
        "__init__.py", "__main__.py",
    }
    metadata = json.loads((tmp_path / "provenance/metadata.json").read_text(encoding="utf-8"))
    assert metadata["provenance"] == provenance.model_dump(mode="json")
    selected = PersonaModel.load(tmp_path / "provenance").generate(BusinessContext(description="bread recipes"), 1)[0]
    assert selected.strategy == strategy
    assert selected.training_code_sha256 == provenance.training_code_sha256
    assert selected.source_corpus_sha256 == provenance.source_records_sha256
    attribution = selected.source_attribution
    assert attribution.source == "invented" and attribution.revision == "test-1"
    assert attribution.creator is None and attribution.license is None and attribution.source_url is None
    assert attribution.modifications
    assert attribution.metadata_status == "unavailable"


def test_training_code_change_changes_model_revision_without_changing_records(
    training_records: list[TrainingRecord], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bebshax_persona_ml import provenance

    original = PersonaModel.fit(training_records)
    changed_code = {**provenance.training_code_snapshot(), "model.py": "0" * 64}
    monkeypatch.setattr(provenance, "training_code_snapshot", lambda: changed_code)

    changed = PersonaModel.fit(training_records)

    assert original.records == changed.records
    assert original.version != changed.version
    assert original.provenance.training_code_sha256 != changed.provenance.training_code_sha256


@pytest.mark.parametrize("field", ["training_code_sha256", "source_records_sha256", "source_manifest_sha256"])
def test_manifest_tampering_is_rejected_without_an_external_pin(
    training_records: list[TrainingRecord], tmp_path: Path, field: str,
) -> None:
    directory = tmp_path / "tampered"
    PersonaModel.fit(training_records).save(directory)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    metadata["provenance"][field] = "0" * 64
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersonaModelError, match="(?i)provenance|fingerprint|digest"):
        PersonaModel.load(directory)


def test_trusted_expected_manifest_rejects_an_otherwise_valid_replacement(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    from bebshax_persona_ml.provenance import ExpectedArtifactManifest

    directory, replacement = tmp_path / "approved", tmp_path / "replacement"
    original = PersonaModel.fit(training_records)
    original.save(directory)
    expected = ExpectedArtifactManifest(metadata_sha256=hashlib.sha256((directory / "metadata.json").read_bytes()).hexdigest())
    assert PersonaModel.load(directory, expected_manifest=expected).version == original.version
    PersonaModel.fit(training_records, ModelConfig(seed=7)).save(replacement)
    assert PersonaModel.load(replacement).version != original.version

    with pytest.raises(PersonaModelError, match="(?i)expected.*manifest"):
        PersonaModel.load(replacement, expected_manifest=expected)
    with pytest.raises(PersonaModelError, match="(?i)expected.*manifest"):
        PersonaModel.load(directory, expected_manifest=expected.model_dump())
    with pytest.raises(ValidationError):
        ExpectedArtifactManifest(metadata_sha256="not-a-digest")


def test_local_training_code_verification_is_explicit_and_does_not_break_frozen_artifacts(
    training_records: list[TrainingRecord], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bebshax_persona_ml import provenance

    directory = tmp_path / "frozen"
    PersonaModel.fit(training_records).save(directory)
    assert PersonaModel.load(directory, verify_training_code=True).provenance
    changed_code = {**provenance.training_code_snapshot(), "pipeline.py": "0" * 64}
    monkeypatch.setattr(provenance, "training_code_snapshot", lambda: changed_code)

    assert PersonaModel.load(directory).provenance
    with pytest.raises(PersonaModelError, match="(?i)training code"):
        PersonaModel.load(directory, verify_training_code=True)


@pytest.mark.parametrize("library", ["numpy", "scipy", "sklearn"])
def test_lexical_manifest_keeps_exact_numeric_runtime_checks(
    training_records: list[TrainingRecord], tmp_path: Path, library: str,
) -> None:
    directory = tmp_path / "runtime"
    PersonaModel.fit(training_records, ModelConfig(strategy="lexical", lexical_weight=1.0)).save(directory)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    metadata["runtime"][library] = "0.0.0"
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersonaModelError, match="(?i)runtime"):
        PersonaModel.load(directory)


@pytest.mark.parametrize("validation", ["validate_manifest", "load"])
@pytest.mark.parametrize("strategy, corruption", [
    ("lexical", "unexpected_topics"), ("lexical", "legacy_schema"),
    ("nmf", "missing_topics"), ("nmf", "excess_topics"),
])
def test_manifest_and_load_reject_inconsistent_strategy_dimensions(
    training_records: list[TrainingRecord], tmp_path: Path,
    validation: str, strategy: str, corruption: str,
) -> None:
    directory = tmp_path / "inconsistent-manifest"
    PersonaModel.fit(training_records, ModelConfig(
        strategy=strategy, lexical_weight=1.0,
    )).save(directory)
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if corruption == "legacy_schema":
        metadata["schema_version"] = 1
        metadata.pop("provenance")
    elif corruption == "unexpected_topics":
        metadata["n_topics"] = 1
    elif corruption == "missing_topics":
        metadata["n_topics"] = 0
    else:
        metadata["n_topics"] = min(metadata["n_records"], metadata["n_features"]) + 1
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersonaModelError, match="(?i)strategy|topic|dimension|schema"):
        getattr(PersonaModel, validation)(directory)


def test_fit_rejects_provenance_for_different_training_records(training_records: list[TrainingRecord]) -> None:
    from bebshax_persona_ml.provenance import ModelProvenance

    provenance = ModelProvenance.from_records(training_records)
    with pytest.raises(PersonaModelError, match="(?i)provenance|source.*digest"):
        PersonaModel.fit(list(reversed(training_records)), provenance=provenance)
    with pytest.raises(PersonaModelError, match="(?i)provenance"):
        PersonaModel.fit(training_records, provenance=provenance.model_dump())


@pytest.mark.parametrize("strategy", ["nmf", "lexical"])
@pytest.mark.parametrize("schema_version", [2, 3])
@pytest.mark.parametrize("identity_field", ["source", "revision"])
def test_load_rejects_attribution_for_a_different_source_identity(
    training_records: list[TrainingRecord], tmp_path: Path,
    strategy: str, schema_version: int, identity_field: str,
) -> None:
    directory = tmp_path / "wrong-source-attribution"
    model = PersonaModel.fit(training_records, ModelConfig(
        strategy=strategy, lexical_weight=1.0,
    ))
    model._schema_version = schema_version
    model.version = model._revision()
    model.save(directory)
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["provenance"]["source_attributions"][0][identity_field] = "different-source-identity"
    identity = {
        "corpus": metadata["corpus_fingerprint"],
        "config": json.loads((directory / "config.json").read_text(encoding="utf-8")),
        "algorithm": metadata["algorithm"], "provenance": metadata["provenance"],
    }
    if schema_version == 3:
        identity["tokenizer_contract"] = metadata["tokenizer_contract"]
    metadata["model_version"] = fingerprint(identity)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(PersonaModelError, match="(?i)source.*attribution|provenance"):
        PersonaModel.load(directory)


@pytest.mark.parametrize("strategy", ["nmf", "lexical"])
def test_load_allows_attribution_for_sources_filtered_out_of_training_candidates(
    training_records: list[TrainingRecord], tmp_path: Path, strategy: str,
) -> None:
    incomplete = training_records[0].model_copy(update={
        "record_id": "incomplete-other-source", "source": "other-source",
        "revision": "other-revision", "goals": [],
    }, deep=True)
    model = PersonaModel.fit([*training_records, incomplete], ModelConfig(
        strategy=strategy, lexical_weight=1.0,
    ))
    model.save(tmp_path / "filtered-source")

    restored = PersonaModel.load(tmp_path / "filtered-source")

    assert restored.records == training_records
    assert restored.provenance == model.provenance
    selection = restored.generate(BusinessContext(description="bread recipes"), 1)[0]
    assert selection.source_attribution.source == training_records[0].source
    assert selection.source_attribution.revision == training_records[0].revision


@pytest.mark.parametrize("corruption", ["shape", "object", "extra_nmf_array", "topic_count", "algorithm"])
def test_lexical_artifact_rejects_wrong_shapes_pickle_and_strategy_state(
    training_records: list[TrainingRecord], tmp_path: Path, corruption: str,
) -> None:
    directory = tmp_path / "invalid-lexical"
    PersonaModel.fit(training_records, ModelConfig(strategy="lexical", lexical_weight=1.0)).save(directory)
    metadata = json.loads((directory / "metadata.json").read_text())
    if corruption in {"topic_count", "algorithm"}:
        metadata["n_topics" if corruption == "topic_count" else "algorithm"] = 1 if corruption == "topic_count" else "tfidf-nmf-mmr-v1"
        (directory / "metadata.json").write_text(json.dumps(metadata))
    else:
        with np.load(directory / "parameters.npz", allow_pickle=False) as archive:
            arrays = {name: archive[name] for name in archive.files}
        if corruption == "shape":
            arrays["lexical_indptr"] = arrays["lexical_indptr"][:-1]
        elif corruption == "object":
            arrays["idf"] = arrays["idf"].astype(object)
        else:
            arrays["components"] = np.ones((1, 1))
        np.savez(directory / "parameters.npz", **arrays)
        _reseal_file(directory, "parameters.npz")

    with pytest.raises(PersonaModelError):
        PersonaModel.load(directory)


def test_verified_attribution_cannot_claim_missing_creator_or_license() -> None:
    from bebshax_persona_ml.provenance import SourceAttribution

    values = SourceAttribution.unavailable("invented", "test-1").model_dump()
    with pytest.raises(ValidationError):
        SourceAttribution.model_validate({**values, "metadata_status": "verified_ingestion_metadata"})
    with pytest.raises(ValidationError):
        SourceAttribution.model_validate({**values, "creator": "  "})


def test_selection_rejects_mismatched_attribution_identity(training_records: list[TrainingRecord]) -> None:
    from bebshax_persona_ml.provenance import SourceAttribution

    with pytest.raises(ValidationError):
        Selection(record=training_records[0], score=0.5, topic=0, model_version="0" * 64,
                  source_attribution=SourceAttribution.unavailable("another-source", "test-1"))


@pytest.mark.parametrize("strategy, topic", [("lexical", 0), ("nmf", None)])
def test_selection_rejects_inconsistent_strategy_topic_identity(
    training_records: list[TrainingRecord], strategy: str, topic: int | None,
) -> None:
    with pytest.raises(ValidationError):
        Selection(record=training_records[0], score=0.5, topic=topic,
                  model_version="0" * 64, strategy=strategy)


def test_save_rejects_oversized_provenance_before_writing_payloads(
    training_records: list[TrainingRecord], tmp_path: Path,
) -> None:
    from bebshax_persona_ml.provenance import ModelProvenance

    values = ModelProvenance.from_records(training_records).model_dump(mode="json")
    values["source_attributions"][0]["modifications"] = ["large notice " * 700] * 10
    model = PersonaModel.fit(training_records, provenance=ModelProvenance.model_validate(values))
    directory = tmp_path / "oversized"

    with pytest.raises(PersonaModelError, match="(?i)size|limit"):
        model.save(directory)
    assert not directory.exists() or list(directory.iterdir()) == []