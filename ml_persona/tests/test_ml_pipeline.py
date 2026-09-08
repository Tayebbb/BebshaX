"""Offline lifecycle contracts using tiny, explicitly synthetic local corpora."""

import hashlib
import json
import os
import runpy
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from bebshax_persona_ml.data import TrainingRecord, fingerprint
from bebshax_persona_ml.model import BusinessContext, ModelConfig, PersonaModel

DATASET_ID = "nemotron_personas_usa_ml"
SOURCE = "nvidia/Nemotron-Personas-USA"
REVISION = "a" * 40
PROCESSED = Path("data/processed/ml_persona")
RUN_PROCESS = subprocess.run


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish_source(root: Path, rows: list[dict]) -> dict:
    entry = {
        "dataset_id": DATASET_ID, "hf_repo_id": SOURCE, "pinned_revision": REVISION,
        "training_allowed": True, "profiles": ["ml_persona"],
        "files_or_patterns": ["data/train.parquet"],
    }
    artifacts = {
        "raw": root / "data/raw" / DATASET_ID / "data/train.parquet",
        "card": root / "data/raw" / DATASET_ID / "README.md",
        "processed": root / "data/processed" / f"{DATASET_ID}.jsonl",
    }
    for path in artifacts.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    artifacts["raw"].write_bytes(b"invented fixture shard; never real training data")
    artifacts["card"].write_text("Synthetic fixture card", encoding="utf-8")
    artifacts["processed"].write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8",
    )
    metadata = {
        **entry, "artifact_role": "training", "metadata_version": 1,
        **{f"actual_{name}_sha256": _digest(path) for name, path in artifacts.items()},
        "processed_record_count": len(rows),
    }
    metadata["metadata_sha256"] = fingerprint(metadata)
    metadata_path = root / "data/metadata" / f"{DATASET_ID}.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return entry


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Lifecycle unit tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def source_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    names = "Alpha Bravo Charlie Delta Echo Foxtrot Golf Hotel India Juliet Kilo Lima Mike November Oscar Papa Quebec Romeo Sierra Tango Uniform Victor Whiskey Xray".split()
    domains = ["bread recipes cooking ingredients", "electrical wiring circuits equipment"]
    rows = [{
        "uuid": f"fixture-{index:03d}", "age": 20 + index,
        "persona": f"Fixture {name} is a worker practicing {domains[index % 2]} in district {index}.",
        "occupation": "baker" if index % 2 == 0 else "electrician",
        "professional_persona": f"Practice {domains[index % 2]} professionally.",
        "culinary_persona": f"Enjoy {domains[index % 2]}.",
        "hobbies_and_interests": f"Explore {domains[index % 2]}.",
        "career_goals_and_ambitions": f"Improve {domains[index % 2]}.",
        "travel_persona": f"Limited budget for {domains[index % 2]}.",
        "city": "Fixture City", "country": "USA", "education_level": "vocational",
    } for index, name in enumerate(names)]
    incomplete = {**rows[0], "uuid": "incomplete-first", "travel_persona": "Enjoys local walks."}
    rows = [incomplete, *rows, {**incomplete, "uuid": "incomplete-other", "persona": "Missing Profile enjoys work."},
            {**rows[0], "uuid": "duplicate-name", "persona": "Fixture Alpha has a second source description."},
            {**rows[0], "uuid": "underage", "age": 17}, {**rows[0], "uuid": "overage", "age": 96}]
    entry = _publish_source(tmp_path, rows)
    (tmp_path / "scripts").mkdir()
    for name in ("setup_datasets.py", "persona_ml_dataset.py", "dataset_manifest.py"):
        (tmp_path / "scripts" / name).write_text("", encoding="utf-8")

    def official_verifier(arguments: list[str], **options: object) -> subprocess.CompletedProcess:
        assert arguments[0] == sys.executable and arguments[1] == "-c"
        assert "verify_ml_dataset" in arguments[2]
        assert Path(options["cwd"]) == tmp_path
        metadata = json.loads((tmp_path / "data/metadata" / f"{DATASET_ID}.json").read_text())
        return subprocess.CompletedProcess(arguments, 0, json.dumps({
            "entry": entry, "raw_sha256": metadata["actual_raw_sha256"],
            "processed_sha256": metadata["actual_processed_sha256"],
        }), "")

    monkeypatch.setattr(subprocess, "run", official_verifier)
    return tmp_path


def test_validate_requires_preparation_manifest_without_creating_files(tmp_path: Path) -> None:
    from bebshax_persona_ml import pipeline

    with pytest.raises(FileNotFoundError, match="preparation.json"):
        pipeline.validate(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_prepare_keeps_complete_unique_adults_and_pins_source_fingerprints(source_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    original_path = list(sys.path)
    report = pipeline.prepare(source_case)
    assert sys.path == original_path
    assert report == pipeline.validate(source_case)
    assert report["schema_version"] == 1 and report["seed"] == 42
    assert report["source"]["hf_repo_id"] == SOURCE
    assert report["source"]["revision"] == REVISION
    assert report["statistics"]["rejected"] == 2
    assert report["statistics"]["incomplete"] == 2
    assert report["statistics"]["identity_duplicates"] == 1
    assert report["statistics"]["candidate_count"] == 24
    records = []
    for split in ("train", "validation", "test"):
        path = source_case / PROCESSED / f"{split}.jsonl"
        partition = [TrainingRecord.model_validate_json(line) for line in path.read_text().splitlines()]
        assert partition and [record.record_id for record in partition] == sorted(record.record_id for record in partition)
        assert report["splits"][split]["file_sha256"] == _digest(path)
        assert report["splits"][split]["record_sha256"] == [fingerprint(record.model_dump()) for record in partition]
        records.extend(partition)
    assert len(records) == len({record.name for record in records}) == 24
    assert all(record.pain_points and record.goals and 18 <= record.age <= 95 for record in records)
    assert all(record.source == SOURCE and record.revision == REVISION for record in records)
    assert all(record.documents["persona"] == record.description for record in records)


def test_prepare_is_order_independent_and_supports_root_relative_output(source_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    first = pipeline.prepare(source_case)
    rows_path = source_case / "data/processed" / f"{DATASET_ID}.jsonl"
    _publish_source(source_case, list(reversed([json.loads(line) for line in rows_path.read_text().splitlines()])))
    second = pipeline.prepare(source_case, Path("another/prepared"))
    assert first["dataset_sha256"] == second["dataset_sha256"]
    for split in ("train", "validation", "test"):
        assert (source_case / PROCESSED / f"{split}.jsonl").read_bytes() == (
            source_case / "another/prepared" / f"{split}.jsonl"
        ).read_bytes()


def test_prepare_refuses_overwrite_and_explicit_force_reproduces_splits(source_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    original = pipeline.prepare(source_case)
    with pytest.raises(FileExistsError):
        pipeline.prepare(source_case)
    assert pipeline.prepare(source_case, force=True) == original


@pytest.mark.parametrize("changed", ["train", "raw", "metadata", "processed"])
def test_validate_detects_changed_prepared_or_source_artifacts(source_case: Path, changed: str) -> None:
    from bebshax_persona_ml import pipeline

    pipeline.prepare(source_case)
    paths = {"train": PROCESSED / "train.jsonl", "raw": Path(f"data/raw/{DATASET_ID}/data/train.parquet"),
             "metadata": Path(f"data/metadata/{DATASET_ID}.json"), "processed": Path(f"data/processed/{DATASET_ID}.jsonl")}
    with (source_case / paths[changed]).open("ab") as artifact:
        artifact.write(b"\n")
    with pytest.raises(ValueError, match="(?i)checksum|fingerprint"):
        pipeline.validate(source_case)


def test_prepare_propagates_official_verification_failure_without_creating_splits(
    source_case: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bebshax_persona_ml import pipeline

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1, "", "sensitive external detail"))
    with pytest.raises(ValueError, match="(?i)verification") as failure:
        pipeline.prepare(source_case)
    assert "sensitive" not in str(failure.value)
    assert not (source_case / PROCESSED).exists()


@pytest.mark.parametrize("options", [{"seed": -1}, {"seed": True}, {"validation_fraction": 0},
                                    {"test_fraction": 0.9, "validation_fraction": 0.2}])
def test_prepare_rejects_invalid_split_configuration(source_case: Path, options: dict) -> None:
    from bebshax_persona_ml import pipeline

    with pytest.raises(ValueError):
        pipeline.prepare(source_case, **options)
    assert not (source_case / PROCESSED).exists()


@pytest.fixture
def prepared_case(source_case: Path) -> Path:
    from bebshax_persona_ml import pipeline

    pipeline.prepare(source_case)
    return source_case


def _tiny_config() -> dict:
    return {"model": {"max_features": 200, "max_iter": 40, "temperature": 0.0001},
            "topics": [2], "lexical_weights": [0.35, 0.7], "threads": 1}


def test_train_selects_validation_mrr_keeps_train_only_artifacts_and_full_experiment(prepared_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    directory = prepared_case / PROCESSED
    original = {name: (directory / f"{name}.jsonl").read_bytes() for name in ("train", "validation", "test")}
    report = pipeline.train(prepared_case, config=pipeline.TrainingConfig(**_tiny_config()))
    fitted = PersonaModel.load(directory / "model")
    assert report["schema_version"] == 1 and report["model_version"] == fitted.version
    assert report["selected_config"] == fitted.config.model_dump()
    assert report["selection"]["objective"] == "retrieval.model.mrr"
    assert report["selection"]["split"] == "validation"
    assert report["test_evaluated"] is False
    assert report["sizes"] == {"train": 18, "validation": 3, "test": 3}
    assert len(report["candidates"]) == 2
    expected = sorted(report["candidates"], key=lambda candidate: (
        -candidate["validation"]["retrieval"]["model"]["mrr"],
        json.dumps(candidate["config"], sort_keys=True),
    ))[0]
    assert report["selected_config"] == expected["config"]
    assert report["runtime"].keys() >= {"python", "numpy", "scipy", "sklearn"}
    assert report["hardware"]["threads"] == 1 and report["training_seconds"] >= 0
    assert report["source"]["revision"] == REVISION and report["dataset_sha256"]
    for candidate in report["candidates"]:
        assert candidate["training_seconds"] >= 0 and candidate["iterations"] > 0
        assert isinstance(candidate["convergence_warnings"], list)
        assert candidate["validation"]["retrieval"].keys() >= {"model", "lexical_tfidf", "random", "popular_occupation"}
    assert {record.record_id for record in fitted.records} == {
        json.loads(line)["record_id"] for line in original["train"].splitlines()
    }
    for name, payload in original.items():
        assert (directory / f"{name}.jsonl").read_bytes() == payload
    assert {"metadata.json", "config.json", "vocabulary.json", "records.json", "parameters.npz"} == {
        path.name for path in (directory / "model").iterdir()
    }
    assert json.loads((directory / "experiment.json").read_text()) == report
    assert json.loads((directory / "experiments" / f"{fitted.version}.json").read_text()) == report


def test_tiny_training_changes_selection_with_business_context_and_is_seeded(prepared_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    pipeline.train(prepared_case, config=pipeline.TrainingConfig(**_tiny_config()))
    fitted = PersonaModel.load(prepared_case / PROCESSED / "model")
    for description, occupation in [("bread recipes cooking ingredients", "baker"),
                                    ("electrical wiring circuits equipment", "electrician")]:
        context = BusinessContext(description=description)
        selections = fitted.generate(context, 1, seed=7)
        assert selections[0].record.occupation == occupation
        assert selections == fitted.generate(context, 1, seed=7)


def test_evaluate_only_uses_test_and_does_not_modify_model_or_splits(prepared_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    experiment = pipeline.train(prepared_case, config=pipeline.TrainingConfig(**_tiny_config()))
    directory = prepared_case / PROCESSED
    protected = {path: path.read_bytes() for path in directory.rglob("*") if path.is_file()}
    report = pipeline.evaluate(prepared_case)
    assert report["split"] == "test" and report["model_version"] == experiment["model_version"]
    assert report["metrics"]["retrieval"]["query_count"] == 3
    assert report["metrics"]["generation"]["structural"]["bundle_mismatch_count"] == 0
    assert "proxy" in report["limitation"].lower() and "population" in report["limitation"].lower()
    assert all(path.read_bytes() == payload for path, payload in protected.items())
    assert json.loads((directory / "evaluation.json").read_text()) == report
    with pytest.raises(FileExistsError):
        pipeline.evaluate(prepared_case)


def test_train_refuses_existing_artifacts_and_force_is_explicit(prepared_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    config = pipeline.TrainingConfig(**_tiny_config())
    first = pipeline.train(prepared_case, config=config)
    with pytest.raises(FileExistsError):
        pipeline.train(prepared_case, config=config)
    second = pipeline.train(prepared_case, config=config, force=True)
    assert second["model_version"] == first["model_version"]


@pytest.mark.parametrize("config", [{"topics": []}, {"topics": [0]}, {"lexical_weights": []},
                                    {"lexical_weights": [1.0]}, {"lexical_weights": [float("nan")]},
                                    {"threads": 0}, {"threads": True}, {"threads": 65},
                                    {"model": {"device": "cuda"}}, {"unknown": "forbidden"}])
def test_training_config_rejects_invalid_values(config: dict) -> None:
    from bebshax_persona_ml import pipeline

    with pytest.raises(ValueError):
        pipeline.TrainingConfig(**config)


def test_default_grid_is_cpu_bounded_and_never_pure_lexical() -> None:
    from bebshax_persona_ml import pipeline

    config = pipeline.TrainingConfig()
    assert config.topics == [16, 32] and config.lexical_weights == [0.35, 0.7]
    assert config.model.max_iter == 300 and config.model.seed == 42
    assert config.threads == 2


def test_train_records_convergence_warning_and_iterations(prepared_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    report = pipeline.train(prepared_case, config=pipeline.TrainingConfig(
        model=ModelConfig(max_iter=1), topics=[2], lexical_weights=[0.35], threads=1,
    ))
    assert report["candidates"][0]["iterations"] == 1
    assert report["candidates"][0]["convergence_warnings"]


@pytest.mark.parametrize("destination", ["test.jsonl", "train.jsonl", "preparation.json"])
def test_training_report_cannot_overwrite_prepared_inputs_even_with_force(prepared_case: Path, destination: str) -> None:
    from bebshax_persona_ml import pipeline

    path = prepared_case / PROCESSED / destination
    before = path.read_bytes()
    with pytest.raises(ValueError, match="(?i)protected|output"):
        pipeline.train(prepared_case, config=pipeline.TrainingConfig(**_tiny_config()), report_path=path, force=True)
    assert path.read_bytes() == before


def _invoke(capsys: pytest.CaptureFixture, root: Path, *arguments: str) -> tuple[int, dict]:
    from bebshax_persona_ml.cli import main

    status = main(["--root", str(root), *arguments])
    captured = capsys.readouterr()
    assert not captured.err
    return status, json.loads(captured.out)


def test_cli_offline_order_end_to_end_preserves_source_grounding_and_seed(
    source_case: Path, capsys: pytest.CaptureFixture,
) -> None:
    business = {"description": "affordable bread recipes cooking ingredients", "location": "Requested City"}
    (source_case / "business.json").write_text(json.dumps(business))
    (source_case / "config.json").write_text(json.dumps(_tiny_config()))
    for command in [("prepare",), ("validate",), ("train", "--config", "config.json"), ("evaluate",)]:
        status, result = _invoke(capsys, source_case, *command)
        assert status == 0 and result["ok"] is True and result["command"] == command[0]
        assert isinstance(result["result"], dict)
    arguments = ("generate", "--input", "business.json", "--num-personas", "5", "--seed", "42")
    status, result = _invoke(capsys, source_case, *arguments, "--output", "generated.json")
    assert status == 0 and len(result["result"]["personas"]) == 5
    assert result["result"] == json.loads((source_case / "generated.json").read_text())
    assert _invoke(capsys, source_case, *arguments)[1] == result
    original = PersonaModel.load(source_case / PROCESSED / "model")
    records = {record.record_id: record for record in original.records}
    for persona in result["result"]["personas"]:
        source = records[persona["id"]]
        assert persona["identity"]["name"] == source.name
        assert persona["identity"]["description"] == source.description
        assert persona["demographics"]["location"] == source.location
        assert persona["source"]["repo_id"] == SOURCE and persona["source"]["revision"] == REVISION
        assert persona["source"]["documents"] == source.documents
        assert persona["synthetic"] is True and persona["provenance"]["observed"] is False
        assert persona["provenance"]["evidence_status"] == "NOT_OBSERVED"
        assert persona["model"]["version"] == original.version
        assert persona["model"]["selection_score"] >= 0 and "confidence" not in persona["model"]
        assert "income" not in persona["demographics"] and "ocean" not in persona
        assert persona["warnings"]
        for field in ("goals", "pain_points", "behaviors"):
            assert [claim["text"] for claim in persona[field]] == getattr(source, field)
            assert all(claim["evidence_status"] == "NOT_OBSERVED" for claim in persona[field])
    files = {path: path.read_bytes() for path in (source_case / PROCESSED).rglob("*") if path.is_file()}
    status, smoke = _invoke(capsys, source_case, "smoke", "--input", "business.json")
    assert status == 0 and smoke["ok"] is True
    assert {stage["name"] for stage in smoke["result"]["stages"]} == {"source", "prepared", "model", "generation"}
    assert all(stage["ok"] for stage in smoke["result"]["stages"])
    assert smoke["result"]["num_personas"] == 5
    assert all(path.read_bytes() == payload for path, payload in files.items())


@pytest.mark.parametrize("arguments, code", [
    (("generate",), "usage_error"), (("generate", "--input", "missing.json"), "missing_input"),
    (("generate", "--input", "business.json", "--num-personas", "0"), "invalid_input"),
    (("generate", "--input", "business.json", "--seed", "-1"), "invalid_input"),
    (("train", "--config", "bad-config.json"), "invalid_input"),
    (("nonsense-secret-value",), "usage_error"), (("--unknown-secret-option",), "usage_error"),
])
def test_cli_errors_are_single_sanitized_stdout_json(
    tmp_path: Path, capsys: pytest.CaptureFixture, arguments: tuple[str, ...], code: str,
) -> None:
    (tmp_path / "business.json").write_text(json.dumps({"description": "bread recipes"}))
    (tmp_path / "bad-config.json").write_text(json.dumps({"api_key": "fixture-secret-must-not-leak"}))
    status, result = _invoke(capsys, tmp_path, *arguments)
    assert status != 0 and result["ok"] is False and result["error"]["code"] == code
    assert "secret" not in json.dumps(result).lower()


@pytest.mark.parametrize("content", ["{broken private-value", "null", "[]", '{"description": 5}',
                                     '{"description": "bread recipes", "unknown": "private-value"}'])
def test_generate_rejects_malformed_or_non_strict_business_json(
    tmp_path: Path, capsys: pytest.CaptureFixture, content: str,
) -> None:
    (tmp_path / "business.json").write_text(content)
    status, result = _invoke(capsys, tmp_path, "generate", "--input", "business.json")
    assert status != 0 and result["error"]["code"] == "invalid_input"
    assert "private-value" not in json.dumps(result)


def test_smoke_reports_local_failed_stages_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    status, result = _invoke(capsys, tmp_path, "smoke")
    assert status != 0 and result["ok"] is False
    assert any(not stage["ok"] for stage in result["result"]["stages"])
    assert list(tmp_path.iterdir()) == []


def test_download_delegates_only_setup_script_with_active_python_and_cwd(
    source_case: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    calls = []

    def setup(arguments: list[str], **options: object) -> subprocess.CompletedProcess:
        calls.append((arguments, options))
        return subprocess.CompletedProcess(arguments, 0, "upstream non-JSON output", "upstream logs")

    monkeypatch.setattr(subprocess, "run", setup)
    status, result = _invoke(capsys, source_case, "download", "--force")
    assert status == 0 and result["ok"] is True
    assert len(calls) == 1
    arguments, options = calls[0]
    assert arguments == [sys.executable, str(source_case / "scripts/setup_datasets.py"), "--profile", "ml_persona", "--force"]
    assert options["cwd"] == source_case and options["capture_output"] is True
    assert "upstream" not in json.dumps(result)


def test_download_failure_never_echoes_subprocess_arguments_or_logs(
    source_case: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 3, "private-output", "private-error"))
    status, result = _invoke(capsys, source_case, "download")
    assert status != 0 and result["error"]["code"] == "lifecycle_error"
    assert "private" not in json.dumps(result)


def test_module_entrypoints_and_help_default_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    from bebshax_persona_ml.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["--help"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert main(["validate"]) != 0
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "missing_input"
    monkeypatch.setattr(sys, "argv", ["bebshax-persona-ml", "--help"])
    with pytest.raises(SystemExit) as exit_status:
        runpy.run_module("bebshax_persona_ml", run_name="__main__")
    assert exit_status.value.code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_prepare_exact_content_duplicates_choose_same_id_after_reordering(source_case: Path) -> None:
    from bebshax_persona_ml import pipeline

    rows_path = source_case / "data/processed" / f"{DATASET_ID}.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text().splitlines()]
    rows.append({**rows[1], "uuid": "same-content-another-id"})
    _publish_source(source_case, rows)
    first = pipeline.prepare(source_case)
    _publish_source(source_case, list(reversed(rows)))
    second = pipeline.prepare(source_case, Path("second/prepared"))
    assert first["dataset_sha256"] == second["dataset_sha256"]
    assert first["statistics"]["duplicate_names"] == second["statistics"]["duplicate_names"] == 1


@pytest.mark.parametrize("changes", [{"training_allowed": False}, {"profiles": ["minimal"]},
                                      {"dataset_id": "../uploads"}, {"files_or_patterns": ["../../private.json"]},
                                      {"pinned_revision": "main"}])
def test_prepare_rejects_unapproved_or_unsafe_verifier_metadata(
    source_case: Path, monkeypatch: pytest.MonkeyPatch, changes: dict,
) -> None:
    from bebshax_persona_ml import pipeline

    original = subprocess.run

    def changed_entry(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        result = original(*args, **kwargs)
        payload = json.loads(result.stdout)
        payload["entry"].update(changes)
        result.stdout = json.dumps(payload)
        return result

    monkeypatch.setattr(subprocess, "run", changed_entry)
    with pytest.raises(ValueError):
        pipeline.prepare(source_case)
    assert not (source_case / PROCESSED).exists()


def _rehash_partition(root: Path, name: str, rows: list[dict]) -> None:
    directory = root / PROCESSED
    rows.sort(key=lambda row: row["record_id"])
    path = directory / f"{name}.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    metadata = json.loads((directory / "preparation.json").read_text())
    metadata["splits"][name] = {"count": len(rows), "file_sha256": _digest(path),
                                 "records_sha256": fingerprint(rows), "record_sha256": [fingerprint(row) for row in rows]}
    all_records = [json.loads(line) for split in ("train", "validation", "test")
                   for line in (directory / f"{split}.jsonl").read_text().splitlines()]
    metadata["dataset_sha256"] = fingerprint(sorted(all_records, key=lambda row: row["record_id"]))
    metadata["preparation_sha256"] = fingerprint({key: value for key, value in metadata.items() if key != "preparation_sha256"})
    (directory / "preparation.json").write_text(json.dumps(metadata), encoding="utf-8")


@pytest.mark.parametrize("field", ["record_id", "name", "description", "format_description"])
def test_validate_rejects_rehashed_cross_split_identity_overlap(prepared_case: Path, field: str) -> None:
    from bebshax_persona_ml import pipeline

    directory = prepared_case / PROCESSED
    training = json.loads((directory / "train.jsonl").read_text().splitlines()[0])
    rows = [json.loads(line) for line in (directory / "test.jsonl").read_text().splitlines()]
    if field == "format_description":
        rows[0]["description"] = training["description"].upper().replace(".", "!")
    else:
        rows[0][field] = training[field]
    _rehash_partition(prepared_case, "test", rows)
    with pytest.raises(ValueError, match="(?i)identit|overlap|duplicate"):
        pipeline.validate(prepared_case)


@pytest.mark.parametrize("changes", [{"age": "21"}, {"age": 17}, {"private_field": "forbidden"},
                                     {"goals": []}, {"source": "private-study"}])
def test_validate_checks_every_record_even_when_all_hashes_are_recomputed(prepared_case: Path, changes: dict) -> None:
    from bebshax_persona_ml import pipeline

    path = prepared_case / PROCESSED / "validation.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0].update(changes)
    _rehash_partition(prepared_case, "validation", rows)
    with pytest.raises(ValueError):
        pipeline.validate(prepared_case)


@pytest.mark.parametrize("relative_path", [f"data/metadata/{DATASET_ID}.json", f"data/raw/{DATASET_ID}/source.json",
                                          "data/processed/ml_persona/test.jsonl", "data/processed/ml_persona/model/config.json"])
def test_forced_generation_output_cannot_overwrite_source_split_or_model(
    prepared_case: Path, capsys: pytest.CaptureFixture, relative_path: str,
) -> None:
    from bebshax_persona_ml import pipeline

    pipeline.train(prepared_case, config=pipeline.TrainingConfig(**_tiny_config()))
    (prepared_case / "business.json").write_text('{"description": "bread recipes cooking"}')
    target = prepared_case / relative_path
    before = target.read_bytes() if target.exists() else None
    status, result = _invoke(capsys, prepared_case, "generate", "--input", "business.json",
                            "--output", relative_path, "--force")
    assert status != 0 and result["ok"] is False
    assert target.read_bytes() == before if before is not None else not target.exists()


def test_generate_unnamed_profiles_keep_identifier_with_note(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    record = TrainingRecord(record_id="unnamed-source", source=SOURCE, revision=REVISION, age=21,
                            occupation="student", description="unnamed source cooks bread recipes",
                            goals=["Improve recipes."], pain_points=["Limited budget."])
    model = PersonaModel.fit([record], ModelConfig(n_topics=1))
    model.save(tmp_path / "portable-model")
    (tmp_path / "business.json").write_text('{"description": "bread recipes cooking"}')
    status, result = _invoke(capsys, tmp_path, "generate", "--input", "business.json", "--model", "portable-model", "--num-personas", "1")
    assert status == 0
    persona = result["result"]["personas"][0]
    assert persona["identity"]["name"] == "unnamed-source"
    assert any("No source name" in note for note in persona["warnings"])


@pytest.mark.parametrize("path", ["../outside", "/outside-root"])
def test_cli_rejects_paths_outside_explicit_root(tmp_path: Path, capsys: pytest.CaptureFixture, path: str) -> None:
    status, result = _invoke(capsys, tmp_path, "validate", "--data-dir", path)
    assert status != 0 and result["error"]["code"] == "lifecycle_error"


def test_actual_verification_subprocess_uses_only_root_fixture_scripts(
    source_case: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bebshax_persona_ml import pipeline

    metadata = json.loads((source_case / f"data/metadata/{DATASET_ID}.json").read_text())
    entry = {key: metadata[key] for key in ("dataset_id", "hf_repo_id", "pinned_revision", "training_allowed", "profiles", "files_or_patterns")}
    (source_case / "scripts/dataset_manifest.py").write_text(
        "import json\nfrom types import SimpleNamespace\n"
        f"entry = json.loads({json.dumps(entry)!r})\n"
        "ML_DATASET_MANIFEST = [SimpleNamespace(**entry, to_dict=lambda: entry)]\n", encoding="utf-8",
    )
    (source_case / "scripts/persona_ml_dataset.py").write_text(
        "import json\ndef verify_ml_dataset(entry, raw_dir, processed_dir, metadata_dir):\n"
        "    metadata = json.loads((metadata_dir / (entry.dataset_id + '.json')).read_text())\n"
        "    return metadata['actual_raw_sha256'], metadata['actual_processed_sha256']\n", encoding="utf-8",
    )
    monkeypatch.setattr(subprocess, "run", RUN_PROCESS)
    assert pipeline.prepare(source_case)["source"]["hf_repo_id"] == SOURCE


def test_fresh_process_offline_lifecycle_imports_no_backend_provider_torch_or_ingestion(
    prepared_case: Path,
) -> None:
    (prepared_case / "config.json").write_text(json.dumps(_tiny_config()))
    (prepared_case / "business.json").write_text('{"description": "bread recipes cooking"}')
    program = """import importlib.abc, socket, sys
class BlockExternal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'bebshax', 'torch', 'scripts', 'huggingface_hub', 'fastparquet', 'openai', 'anthropic', 'freellmpool'}:
            raise ImportError('Forbidden offline import')
sys.meta_path.insert(0, BlockExternal())
def no_network(*args, **kwargs):
    raise AssertionError('Network forbidden')
socket.socket.connect = no_network
socket.create_connection = no_network
from bebshax_persona_ml.cli import main
for arguments in [['validate'], ['train', '--config', 'config.json'], ['evaluate'],
                  ['generate', '--input', 'business.json'], ['smoke']]:
    if main(['--root', sys.argv[1], *arguments]):
        raise SystemExit(1)
"""
    completed = RUN_PROCESS([sys.executable, "-c", program, str(prepared_case)], cwd=prepared_case,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    results = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(results) == 5 and all(result["ok"] for result in results)


def test_cli_custom_paths_and_grid_overrides_are_root_relative(
    source_case: Path, capsys: pytest.CaptureFixture,
) -> None:
    from bebshax_persona_ml.cli import main

    (source_case / "config.json").write_text(json.dumps(_tiny_config()))
    assert _invoke(capsys, source_case, "prepare", "--output", "custom/prepared")[0] == 0
    status = main(["train", "--root", str(source_case), "--data-dir", "custom/prepared",
                   "--model", "artifacts/fitted", "--report", "reports/latest.json", "--config", "config.json",
                   "--topics", "3", "--lexical-weights", "0.5", "--seed", "7", "--threads", "1"])
    report = json.loads(capsys.readouterr().out)["result"]
    assert status == 0 and len(report["candidates"]) == 1
    assert report["selected_config"]["n_topics"] == 3
    assert report["selected_config"]["lexical_weight"] == 0.5 and report["selected_config"]["seed"] == 7
    assert report["hardware"]["threads"] == 1
    assert json.loads((source_case / "reports/latest.json").read_text()) == report
    status, result = _invoke(capsys, source_case, "evaluate", "--data-dir", "custom/prepared", "--model", "artifacts/fitted",
                            "--report", "reports/audit.json", "--seed", "7")
    assert status == 0 and result["result"]["seed"] == 7
    assert not (source_case / PROCESSED).exists()


def test_train_cannot_overwrite_configuration_input_even_with_force(
    prepared_case: Path, capsys: pytest.CaptureFixture,
) -> None:
    config_path = prepared_case / "config.json"
    config_path.write_text(json.dumps(_tiny_config()))
    original = config_path.read_bytes()
    status, result = _invoke(capsys, prepared_case, "train", "--config", "config.json", "--report", "config.json", "--force")
    assert status != 0 and result["ok"] is False
    assert config_path.read_bytes() == original
    assert not (prepared_case / PROCESSED / "model").exists()


def test_cli_help_includes_selected_subcommand_arguments(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    status, result = _invoke(capsys, tmp_path, "train", "--help")
    assert status == 0
    assert all(option in result["result"]["usage"] for option in ("--config", "--topics", "--lexical-weights", "--report"))


@pytest.mark.parametrize("destination", ["data/raw", "data/metadata", "data/uploads"])
def test_prepare_cannot_write_into_reserved_source_directories(source_case: Path, destination: str) -> None:
    from bebshax_persona_ml import pipeline

    with pytest.raises(ValueError, match="(?i)protected"):
        pipeline.prepare(source_case, Path(destination), force=True)
    assert not (source_case / destination / "train.jsonl").exists()