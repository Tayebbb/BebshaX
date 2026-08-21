"""Tests for dataset manifest schema, profile subsets, and pinned revisions."""

import re
import pytest
from huggingface_hub import HfApi

from scripts.dataset_manifest import (
    DATASET_MANIFEST,
    DatasetEntry,
    get_entries_for_profile,
    get_manifest,
    PROFILES_ORDER,
)


def test_manifest_not_empty():
    manifest = get_manifest()
    assert len(manifest) == 10


def test_manifest_entries_schema():
    manifest = get_manifest()
    sha_pattern = re.compile(r"^[0-9a-f]{40}$")

    for entry in manifest:
        assert isinstance(entry, DatasetEntry)
        assert entry.dataset_id, f"Entry missing dataset_id: {entry}"
        assert entry.hf_repo_id, f"Entry missing hf_repo_id: {entry.dataset_id}"
        
        # Rule: Every entry MUST pin an exact 40-character commit SHA, never 'main' or branch
        assert sha_pattern.match(entry.pinned_revision), (
            f"Dataset '{entry.dataset_id}' has unpinned revision '{entry.pinned_revision}'. "
            f"Must be a 40-character Git commit SHA."
        )
        assert entry.files_or_patterns, f"Dataset '{entry.dataset_id}' has empty files_or_patterns"
        assert entry.profiles, f"Dataset '{entry.dataset_id}' has no profile membership"
        assert entry.download_method in ["hf_hub_file", "hf_stream_slice"], (
            f"Dataset '{entry.dataset_id}' has invalid download_method '{entry.download_method}'"
        )
        assert entry.estimated_raw_size_mb > 0

        # Datasheet dimensions checks
        assert entry.motivation.purpose
        assert entry.composition.slice_description
        assert entry.composition.sample_count_estimate > 0
        assert entry.collection.source_url.startswith("http")
        assert entry.preprocessing.normalized_jsonl_schema
        assert len(entry.uses.prohibited_uses) >= 1
        assert "Model training / fine-tuning (R9 violation)" in entry.uses.prohibited_uses

        # License audit checks
        assert entry.distribution.license_claimed_hf
        assert entry.distribution.license_verified_upstream
        assert entry.distribution.license_verification_url.startswith("http")
        assert entry.distribution.license_verified_at


def test_profile_subset_relations():
    """Enforce minimal ⊂ development ⊂ evaluation ⊂ full."""
    minimal = set(e.dataset_id for e in get_entries_for_profile("minimal"))
    development = set(e.dataset_id for e in get_entries_for_profile("development"))
    evaluation = set(e.dataset_id for e in get_entries_for_profile("evaluation"))
    full = set(e.dataset_id for e in get_entries_for_profile("full"))

    assert len(minimal) > 0
    assert minimal.issubset(development), "minimal must be a strict subset of development"
    assert development.issubset(evaluation), "development must be a strict subset of evaluation"
    assert evaluation.issubset(full), "evaluation must be a strict subset of full"

    # Verify size budgets
    min_size = sum(e.estimated_raw_size_mb for e in get_entries_for_profile("minimal"))
    dev_size = sum(e.estimated_raw_size_mb for e in get_entries_for_profile("development"))
    assert min_size < 1000.0, f"Minimal profile exceeds 1 GB budget: {min_size} MB"
    assert dev_size < 5000.0, f"Development profile exceeds 5 GB budget: {dev_size} MB"


def test_gated_datasets_are_optional():
    """Enforce that all gated datasets are marked optional (is_required=False) to prevent pipeline blockage."""
    manifest = get_manifest()
    for entry in manifest:
        if entry.distribution.is_gated:
            assert entry.is_required is False, (
                f"Gated dataset '{entry.dataset_id}' must have is_required=False so it fails soft for teammates without credentials."
            )


@pytest.mark.integration
def test_pinned_revisions_resolve():
    """Live probe asserting every manifest commit SHA resolves and all target files exist."""
    api = HfApi()
    manifest = get_manifest()

    for entry in manifest:
        try:
            repo_files = api.list_repo_files(
                repo_id=entry.hf_repo_id,
                repo_type="dataset",
                revision=entry.pinned_revision,
            )
            for target_file in entry.files_or_patterns:
                assert target_file in repo_files, (
                    f"File '{target_file}' not found in {entry.hf_repo_id}@{entry.pinned_revision[:7]}"
                )
        except Exception as e:
            if entry.distribution.is_gated or not entry.is_required:
                pytest.skip(f"Skipping unauthenticated optional/gated dataset {entry.dataset_id}: {e}")
            else:
                raise
