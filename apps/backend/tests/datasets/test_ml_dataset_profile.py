"""Offline contracts for the isolated, synthetic-only ML dataset profile."""

import hashlib
import importlib
import json
import shutil
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fastparquet
import huggingface_hub
import pandas
import pytest

from bebshax.persona.evidence import DATASET_ROLES, EvidenceStore
from scripts.dataset_manifest import DatasetEntry, PROFILES_ORDER, get_entries_for_profile, get_manifest


DATASET_ID = "nemotron_personas_usa_ml"
REVISION = "5b4cd35ab46490c1da1bd2b5a2324d6f871be180"
SHARD = "data/train-00000-of-00011.parquet"


def test_ml_profile_is_independent_of_unchanged_legacy_hierarchy() -> None:
    assert PROFILES_ORDER == ["minimal", "development", "evaluation", "full"]
    entries = get_entries_for_profile("ml_persona")
    assert [entry.dataset_id for entry in entries] == [DATASET_ID]
    assert entries[0].profiles == ["ml_persona"]
    for profile in PROFILES_ORDER:
        assert DATASET_ID not in {entry.dataset_id for entry in get_entries_for_profile(profile)}


def test_training_permission_requires_explicit_catalog_opt_in() -> None:
    legacy = get_manifest()
    assert len(legacy) == 10
    assert all(entry.training_allowed is False for entry in legacy)
    catalog = get_manifest(include_training=True)
    assert len(catalog) == 11
    assert [entry.dataset_id for entry in catalog if entry.training_allowed] == [DATASET_ID]
    assert set(DATASET_ROLES).issuperset(entry.dataset_id for entry in catalog)


def test_ml_source_is_pinned_public_synthetic_and_bounded() -> None:
    entry = get_entries_for_profile("ml_persona")[0]
    assert entry.hf_repo_id == "nvidia/Nemotron-Personas-USA"
    assert entry.pinned_revision == REVISION
    assert entry.files_or_patterns == [SHARD]
    assert entry.composition.sample_count_estimate == 6000
    assert entry.training_allowed is True
    assert entry.is_required is True
    assert entry.distribution.is_gated is False
    assert entry.distribution.license_claimed_hf == "cc-by-4.0"
    assert REVISION in entry.distribution.license_verification_url
    assert "Model training / fine-tuning (R9 violation)" not in entry.uses.prohibited_uses
    assert entry.preprocessing.normalized_jsonl_schema["career_goals_and_ambitions"] == "str"
    assert "sex" not in entry.preprocessing.normalized_jsonl_schema
    assert "zipcode" not in entry.preprocessing.normalized_jsonl_schema


def test_training_dataset_never_supplies_observed_evidence_or_seeds(tmp_path: Path) -> None:
    (tmp_path / f"{DATASET_ID}.jsonl").write_text(
        json.dumps({"persona": "A synthetic adult seeks reliable grocery delivery and better customer support."})
        + "\n",
        encoding="utf-8",
    )
    store = EvidenceStore(tmp_path)
    assert store.available_sources() == {}
    assert store.retrieve("grocery delivery customer support") == []
    assert store.seed_persona("training-is-not-a-generation-seed") is None
    assert DATASET_ROLES[DATASET_ID] == "training"


@pytest.fixture
def source_entry() -> DatasetEntry:
    return get_entries_for_profile("ml_persona")[0]


@pytest.fixture
def synthetic_rows(source_entry: DatasetEntry) -> list[dict[str, Any]]:
    rows = []
    for index in range(40):
        row = {name: f"Synthetic {name} {index}" for name in source_entry.preprocessing.normalized_jsonl_schema}
        row.update(uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic-fixture-{index}")), age=25 + index)
        rows.append(row)
    return rows


def _write_parquet(path: Path, rows: list[dict[str, Any]], group_size: int = 8) -> Path:
    fastparquet.write(str(path), pandas.DataFrame(rows), row_group_offsets=group_size, write_index=False)
    return path


def test_hash_ranked_subset_is_stable_across_row_order_and_row_groups(
    tmp_path: Path, source_entry: DatasetEntry, synthetic_rows: list[dict[str, Any]]
) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    entry = replace(source_entry, composition=replace(source_entry.composition, sample_count_estimate=6))
    first_raw = _write_parquet(tmp_path / "first.parquet", synthetic_rows)
    second_raw = _write_parquet(tmp_path / "reordered.parquet", list(reversed(synthetic_rows)), group_size=3)
    first_output = tmp_path / "first.jsonl"
    second_output = tmp_path / "second.jsonl"

    report = ingest.preprocess_nemotron_personas(entry, first_raw, first_output)
    ingest.preprocess_nemotron_personas(entry, second_raw, second_output)

    expected = sorted(
        synthetic_rows,
        key=lambda row: (
            hashlib.sha256(f"{entry.hf_repo_id}@{REVISION}:{row['uuid']}".encode("utf-8")).hexdigest(),
            row["uuid"],
        ),
    )[:6]
    actual = [json.loads(line) for line in first_output.read_text(encoding="utf-8").splitlines()]
    assert actual == expected
    assert any(row in synthetic_rows[8:] for row in actual)
    assert first_output.read_bytes() == second_output.read_bytes()
    assert report["rows_scanned"] == 40
    assert report["row_groups_scanned"] == 5
    assert report["rows_selected"] == 6
    assert report["selection"]["method"] == "sha256_rank_v1"
    assert report["selection"]["requested_rows"] == 6


def test_projection_preserves_full_unicode_narratives_and_excludes_unapproved_fields(
    tmp_path: Path, source_entry: DatasetEntry, synthetic_rows: list[dict[str, Any]]
) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    row = dict(synthetic_rows[0])
    row["persona"] = "  Synthetic Jos\u00e9 profile. " * 1000 + "\nFull final sentence.  "
    row.update(sex="excluded", zipcode="excluded", hobbies_and_interests_list=["excluded"], income=99999)
    raw = _write_parquet(tmp_path / "full.parquet", [row])
    output = tmp_path / "full.jsonl"

    report = ingest.preprocess_nemotron_personas(source_entry, raw, output)

    actual = json.loads(output.read_text(encoding="utf-8"))
    assert set(actual) == set(source_entry.preprocessing.normalized_jsonl_schema)
    assert actual["persona"] == row["persona"]
    assert actual["career_goals_and_ambitions"] == row["career_goals_and_ambitions"]
    assert b"\r\n" not in output.read_bytes()
    assert "Jos\u00e9".encode("utf-8") in output.read_bytes()
    assert report["max_text_characters"]["persona"] == len(row["persona"])
    assert report["excluded_columns"] == ["hobbies_and_interests_list", "income", "sex", "zipcode"]


def test_inspection_reports_missing_and_invalid_values_without_inventing_them(
    tmp_path: Path, source_entry: DatasetEntry, synthetic_rows: list[dict[str, Any]]
) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    row = dict(synthetic_rows[0])
    row.pop("occupation")
    row["age"] = "unknown"
    row["persona"] = ""
    row["city"] = None
    raw = _write_parquet(tmp_path / "missing.parquet", [row])
    output = tmp_path / "missing.jsonl"

    report = ingest.preprocess_nemotron_personas(source_entry, raw, output)

    actual = json.loads(output.read_text(encoding="utf-8"))
    assert actual["age"] == "unknown"
    assert actual["occupation"] is None
    assert actual["city"] is None
    assert "income" not in actual and "budget" not in actual
    assert report["missing_columns"] == ["occupation"]
    assert report["missing_values"]["occupation"] == 1
    assert report["missing_values"]["city"] == 1
    assert report["missing_values"]["persona"] == 1
    assert report["invalid_values"]["age"] == 1


@pytest.mark.parametrize("identifier", [None, "", "not-a-uuid"])
def test_invalid_uuid_fails_without_replacing_existing_output(
    tmp_path: Path, source_entry: DatasetEntry, synthetic_rows: list[dict[str, Any]], identifier: Any
) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    row = dict(synthetic_rows[0], uuid=identifier)
    raw = _write_parquet(tmp_path / "invalid.parquet", [row])
    output = tmp_path / "existing.jsonl"
    output.write_text("existing artifact\n", encoding="utf-8")

    with pytest.raises(ValueError, match="uuid"):
        ingest.preprocess_nemotron_personas(source_entry, raw, output)

    assert output.read_text(encoding="utf-8") == "existing artifact\n"


def test_duplicate_uuid_fails_closed(
    tmp_path: Path, source_entry: DatasetEntry, synthetic_rows: list[dict[str, Any]]
) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    raw = _write_parquet(tmp_path / "duplicates.parquet", [synthetic_rows[0], synthetic_rows[0]])
    with pytest.raises(ValueError, match="duplicate uuid"):
        ingest.preprocess_nemotron_personas(source_entry, raw, tmp_path / "duplicates.jsonl")


def test_empty_shard_is_rejected(tmp_path: Path, source_entry: DatasetEntry) -> None:
    ingest = importlib.import_module("scripts.persona_ml_dataset")
    raw = tmp_path / "empty.parquet"
    fastparquet.write(str(raw), pandas.DataFrame({"uuid": pandas.Series(dtype="str")}), write_index=False)
    with pytest.raises(ValueError, match="empty"):
        ingest.preprocess_nemotron_personas(source_entry, raw, tmp_path / "empty.jsonl")


@pytest.fixture
def ml_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    setup = importlib.import_module("scripts.setup_datasets")
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    raw = _write_parquet(upstream / "shard.parquet", synthetic_rows)
    card = upstream / "README.md"
    card.write_text("---\nlicense: cc-by-4.0\n---\nNVIDIA synthetic adult profiles.\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw.read_bytes()).hexdigest()
    environment: dict[str, Any] = {
        "setup": setup,
        "raw": raw,
        "card": card,
        "raw_sha": raw_sha,
        "downloads": [],
        "metadata_requests": [],
        "offline": False,
        "file_info": SimpleNamespace(
            path=SHARD, size=raw.stat().st_size,
            lfs=SimpleNamespace(sha256=raw_sha, size=raw.stat().st_size),
        ),
    }

    def fake_paths_info(api: Any, **kwargs: Any) -> list[Any]:
        assert not environment["offline"], "local verification must not request Hub metadata"
        assert api.token is False
        environment["metadata_requests"].append(kwargs)
        return [environment["file_info"]]

    def fake_download(**kwargs: Any) -> str:
        assert not environment["offline"], "local verification must not download"
        assert kwargs.get("token") is False, "ML downloads must explicitly disable credentials"
        environment["downloads"].append(kwargs)
        filename = kwargs["filename"]
        assert filename in {"README.md", SHARD}
        source = card if filename == "README.md" else raw
        destination = Path(kwargs["local_dir"]) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return str(destination)

    def forbid_legacy_verification(*args: Any, **kwargs: Any) -> None:
        pytest.fail("ml_persona must not use online-only legacy verification")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(setup, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(setup, "DATA_DIR", data_dir)
    monkeypatch.setattr(setup, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(setup, "PROCESSED_DIR", data_dir / "processed")
    monkeypatch.setattr(setup, "METADATA_DIR", data_dir / "metadata")
    monkeypatch.setattr(setup, "verify_manifest_online", forbid_legacy_verification)
    monkeypatch.setattr(huggingface_hub.HfApi, "get_paths_info", fake_paths_info)
    monkeypatch.setattr(huggingface_hub.HfApi, "list_repo_files", forbid_legacy_verification)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    monkeypatch.setattr(setup, "hf_hub_download", fake_download)
    return environment


def test_download_records_pinned_unauthenticated_card_lfs_and_local_artifact_hashes(
    source_entry: DatasetEntry, ml_environment: dict[str, Any]
) -> None:
    setup = ml_environment["setup"]
    status, raw_sha, processed_sha = setup.process_dataset(source_entry)

    assert status == "PROCESSED"
    assert raw_sha == ml_environment["raw_sha"]
    assert processed_sha == setup.compute_sha256(setup.PROCESSED_DIR / f"{DATASET_ID}.jsonl")
    requests = ml_environment["downloads"]
    assert [request["filename"] for request in requests] == ["README.md", SHARD]
    for request in requests + ml_environment["metadata_requests"]:
        assert request["repo_id"] == source_entry.hf_repo_id
        assert request["repo_type"] == "dataset"
        assert request["revision"] == REVISION
    assert all(request["token"] is False and request["force_download"] is False for request in requests)
    assert ml_environment["metadata_requests"][0]["paths"] == [SHARD]

    metadata = json.loads((setup.METADATA_DIR / f"{DATASET_ID}.json").read_text(encoding="utf-8"))
    assert metadata["metadata_version"] == 1
    assert metadata["artifact_role"] == "training"
    assert metadata["training_allowed"] is True
    assert metadata["pinned_revision"] == REVISION
    assert metadata["actual_raw_sha256"] == raw_sha == metadata["upstream_raw_sha256"]
    assert metadata["actual_processed_sha256"] == processed_sha
    assert metadata["actual_card_sha256"] == setup.compute_sha256(ml_environment["card"])
    assert metadata["raw_size_bytes"] == ml_environment["raw"].stat().st_size
    assert metadata["processed_record_count"] == 40
    assert metadata["inspection"]["rows_scanned"] == 40
    assert metadata["license_check"] == {"license": "cc-by-4.0", "revision": REVISION, "card_path": "README.md"}
    metadata_sha = metadata.pop("metadata_sha256")
    canonical = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert metadata_sha == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("license_line", ["license: mit", "license: null", "license: [cc-by-4.0, mit]", "language: en"])
def test_unapproved_or_missing_card_license_aborts_before_shard_download(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], license_line: str
) -> None:
    ml_environment["card"].write_text(f"---\n{license_line}\n---\nSynthetic fixture.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="license"):
        ml_environment["setup"].process_dataset(source_entry)
    assert [request["filename"] for request in ml_environment["downloads"]] == ["README.md"]


@pytest.mark.parametrize("defect", ["missing_lfs", "bad_sha", "wrong_sha", "wrong_size", "wrong_path"])
def test_unverifiable_upstream_shard_metadata_is_rejected(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], defect: str
) -> None:
    file_info = ml_environment["file_info"]
    if defect == "missing_lfs":
        file_info.lfs = None
    elif defect == "bad_sha":
        file_info.lfs.sha256 = "git-blob-is-not-a-sha256"
    elif defect == "wrong_sha":
        file_info.lfs.sha256 = "0" * 64
    elif defect == "wrong_size":
        file_info.size += 1
        file_info.lfs.size += 1
    else:
        file_info.path = "another-shard.parquet"
    with pytest.raises(ValueError, match="LFS|SHA-256|size|path"):
        ml_environment["setup"].process_dataset(source_entry)
    assert not (ml_environment["setup"].PROCESSED_DIR / f"{DATASET_ID}.jsonl").exists()


@pytest.mark.parametrize("defect", ["permission", "repository", "revision", "files", "license", "gated", "profile"])
def test_invalid_source_manifest_is_rejected_before_network(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], defect: str
) -> None:
    overrides: dict[str, Any] = {
        "permission": {"training_allowed": False},
        "repository": {"hf_repo_id": "private/unapproved"},
        "revision": {"pinned_revision": "main"},
        "files": {"files_or_patterns": ["../private.parquet"]},
        "license": {"distribution": replace(source_entry.distribution, license_claimed_hf="mit")},
        "gated": {"distribution": replace(source_entry.distribution, is_gated=True)},
        "profile": {"profiles": ["full"]},
    }
    with pytest.raises(ValueError, match="allowlist|training|source|license|profile"):
        ml_environment["setup"].process_dataset(replace(source_entry, **overrides[defect]))
    assert ml_environment["downloads"] == []
    assert ml_environment["metadata_requests"] == []


def test_successful_ingestion_is_idempotent_and_verify_only_is_entirely_offline(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = ml_environment["setup"]
    first = setup.process_dataset(source_entry)
    metadata_path = setup.METADATA_DIR / f"{DATASET_ID}.json"
    original_metadata = metadata_path.read_bytes()
    ml_environment["offline"] = True

    assert setup.process_dataset(source_entry) == ("SKIPPED", first[1], first[2])
    assert setup.run_pipeline("ml_persona", verify_only=True) == 0
    monkeypatch.setattr(sys, "argv", ["setup_datasets.py", "--profile", "ml_persona", "--verify-only"])
    with pytest.raises(SystemExit) as result:
        setup.main()
    assert result.value.code == 0
    assert metadata_path.read_bytes() == original_metadata


@pytest.mark.parametrize("artifact", ["raw", "processed", "card", "metadata", "revision", "missing_metadata"])
def test_local_corruption_fails_verification_and_never_becomes_a_skip(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], artifact: str
) -> None:
    setup = ml_environment["setup"]
    setup.process_dataset(source_entry)
    metadata_path = setup.METADATA_DIR / f"{DATASET_ID}.json"
    paths = {
        "raw": setup.RAW_DIR / DATASET_ID / SHARD,
        "processed": setup.PROCESSED_DIR / f"{DATASET_ID}.jsonl",
        "card": setup.RAW_DIR / DATASET_ID / "README.md",
    }
    if artifact in paths:
        with paths[artifact].open("ab") as output:
            output.write(b"tampered\n")
    elif artifact == "missing_metadata":
        metadata_path.unlink()
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["pinned_revision" if artifact == "revision" else "processed_record_count"] = "corrupt"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    ml_environment["offline"] = True

    assert setup.run_pipeline("ml_persona", verify_only=True) == 1
    with pytest.raises(ValueError, match="metadata|revision|checksum|SHA-256|missing|size"):
        setup.process_dataset(source_entry)


def test_verify_only_fails_when_local_artifacts_do_not_exist(ml_environment: dict[str, Any]) -> None:
    ml_environment["offline"] = True
    assert ml_environment["setup"].run_pipeline("ml_persona", verify_only=True) == 1
    assert ml_environment["downloads"] == []


def test_force_really_redownloads_and_repairs_local_corruption(
    source_entry: DatasetEntry, ml_environment: dict[str, Any]
) -> None:
    setup = ml_environment["setup"]
    first = setup.process_dataset(source_entry)
    (setup.PROCESSED_DIR / f"{DATASET_ID}.jsonl").write_text("corrupt\n", encoding="utf-8")

    assert setup.process_dataset(source_entry, force=True) == first
    assert len(ml_environment["downloads"]) == 4
    assert all(request["force_download"] is True for request in ml_environment["downloads"][2:])
    ml_environment["offline"] = True
    assert setup.run_pipeline("ml_persona", verify_only=True) == 0


@pytest.mark.parametrize("checksum_field", ["raw_sha256", "processed_sha256"])
def test_manifest_checksum_mismatch_aborts_without_publishing_artifacts(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], checksum_field: str
) -> None:
    setup = ml_environment["setup"]
    entry = replace(source_entry, **{checksum_field: "0" * 64})
    with pytest.raises(ValueError, match="SHA-256|checksum"):
        setup.process_dataset(entry)
    assert not (setup.PROCESSED_DIR / f"{DATASET_ID}.jsonl").exists()
    assert not (setup.METADATA_DIR / f"{DATASET_ID}.json").exists()


def test_generated_documentation_and_sources_are_deterministic_manifest_projections(
    source_entry: DatasetEntry, ml_environment: dict[str, Any]
) -> None:
    setup = ml_environment["setup"]
    setup.generate_datasets_md(get_manifest(include_training=True))
    doc_path = setup.DATA_DIR / "DATASETS.md"
    sources_path = setup.REPO_ROOT / "ml_persona" / "SOURCES.json"
    documentation = doc_path.read_text(encoding="utf-8")
    assert "THIS IS NOT A TRAINING PROJECT" not in documentation
    assert "| `training` |" in documentation
    assert "--profile ml_persona --verify-only" in documentation
    assert "UCI Restaurant Consumer Data" in documentation
    assert "138" in documentation and "1,161" in documentation and "2012" in documentation
    assert "income" in documentation and "unknown" in documentation
    assert "hypotheses" in documentation and "pain_points" in documentation
    assert "Bangladesh" in documentation
    projection = json.loads(sources_path.read_text(encoding="utf-8"))
    assert projection["schema_version"] == 1
    assert projection["generated_from"] == "scripts/dataset_manifest.py"
    assert projection["profile"] == "ml_persona"
    assert projection["sources"] == [source_entry.to_dict()]
    decisions = {decision["name"]: decision["status"] for decision in projection["research_decisions"]}
    assert decisions == {
        "NVIDIA Nemotron-Personas-USA": "used",
        "Google Synthetic-Persona-Chat": "not_used",
        "PersonaHub": "not_used",
        "UCI Restaurant Consumer Data": "not_used",
        "MiniLM": "not_a_dataset",
    }
    original = (doc_path.read_bytes(), sources_path.read_bytes())
    setup.generate_datasets_md(get_manifest(include_training=True))
    assert original == (doc_path.read_bytes(), sources_path.read_bytes())
    assert b"\r\n" not in sources_path.read_bytes()
    assert ml_environment["downloads"] == []


def test_ml_pipeline_writes_the_complete_catalog_and_source_projection(ml_environment: dict[str, Any]) -> None:
    setup = ml_environment["setup"]
    assert setup.run_pipeline("ml_persona") == 0
    documentation = (setup.DATA_DIR / "DATASETS.md").read_text(encoding="utf-8")
    assert f"### `{DATASET_ID}`" in documentation
    assert "### `personahub_sample`" in documentation
    assert (setup.REPO_ROOT / "ml_persona" / "SOURCES.json").is_file()


def test_required_ml_license_failure_sets_pipeline_exit_code(ml_environment: dict[str, Any]) -> None:
    ml_environment["card"].write_text("---\nlicense: mit\n---\nRejected license.\n", encoding="utf-8")
    assert ml_environment["setup"].run_pipeline("ml_persona") == 1


def test_malformed_card_license_is_a_clear_validation_failure(
    source_entry: DatasetEntry, ml_environment: dict[str, Any]
) -> None:
    ml_environment["card"].write_text("---\nlicense: [\n---\nInvalid metadata.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="license|card"):
        ml_environment["setup"].process_dataset(source_entry)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("hf_repo_id", "unapproved/private"),
        ("pinned_revision", "0" * 40),
        ("training_allowed", False),
        ("files_or_patterns", ["../unapproved.parquet"]),
        ("upstream_raw_sha256", "0" * 64),
        ("processed_record_count", 41),
        ("license_check", {"license": "mit", "revision": REVISION, "card_path": "README.md"}),
    ],
)
def test_local_verification_rejects_wrong_provenance_even_with_recomputed_metadata_hash(
    source_entry: DatasetEntry, ml_environment: dict[str, Any], field_name: str, value: Any
) -> None:
    setup = ml_environment["setup"]
    setup.process_dataset(source_entry)
    metadata_path = setup.METADATA_DIR / f"{DATASET_ID}.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field_name] = value
    metadata.pop("metadata_sha256")
    canonical = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    metadata["metadata_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    ml_environment["offline"] = True

    assert setup.run_pipeline("ml_persona", verify_only=True) == 1


def test_first_run_hashes_can_be_pinned_later_without_invalidating_local_artifacts(
    source_entry: DatasetEntry, ml_environment: dict[str, Any]
) -> None:
    setup = ml_environment["setup"]
    _, raw_sha, output_sha = setup.process_dataset(source_entry)
    pinned = replace(source_entry, raw_sha256=raw_sha, processed_sha256=output_sha)
    ml_environment["offline"] = True
    assert setup.process_dataset(pinned) == ("SKIPPED", raw_sha, output_sha)