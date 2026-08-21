"""Offline unit tests for pipeline idempotence and checksum verification."""

import json
from pathlib import Path
import pytest

from scripts.setup_datasets import compute_sha256, process_dataset
from scripts.dataset_manifest import DatasetEntry, DatasheetMotivation, DatasheetComposition, DatasheetCollection, DatasheetPreprocessing, DatasheetUses, DatasheetDistribution


def test_compute_sha256(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("hello bebshax datasets", encoding="utf-8")
    sha = compute_sha256(f)
    assert len(sha) == 64
    # Recomputing gives same hash
    assert compute_sha256(f) == sha


def test_idempotence_skip_on_matched_checksum(tmp_path, monkeypatch):
    """If processed file exists and checksum matches manifest, processing is skipped (no-op)."""
    import scripts.setup_datasets as sd

    # Redirect directories to tmp_path
    monkeypatch.setattr(sd, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(sd, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(sd, "METADATA_DIR", tmp_path / "metadata")

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True)
    processed_file = processed_dir / "test_ds.jsonl"
    processed_file.write_text('{"id": "1", "data": "test"}\n', encoding="utf-8")
    known_sha = compute_sha256(processed_file)

    entry = DatasetEntry(
        dataset_id="test_ds",
        hf_repo_id="test/repo",
        pinned_revision="1234567890123456789012345678901234567890",
        files_or_patterns=["file.txt"],
        profiles=["minimal"],
        download_method="hf_hub_file",
        preprocessing_fn="preprocess_personahub",
        is_required=True,
        estimated_raw_size_mb=1.0,
        motivation=DatasheetMotivation("test", "test", ["test"]),
        composition=DatasheetComposition("test", "test", 10, "none"),
        collection=DatasheetCollection("https://hf.co", "test", "test"),
        preprocessing=DatasheetPreprocessing("jsonl", "test", {"id": "str"}),
        uses=DatasheetUses(["test"]),
        distribution=DatasheetDistribution("mit", "mit", "https://hf.co", "2026-08-22", False, "test", False),
        processed_sha256=known_sha,
    )

    status, raw_sha, proc_sha = process_dataset(entry, force=False)
    assert status == "SKIPPED"
    assert proc_sha == known_sha
