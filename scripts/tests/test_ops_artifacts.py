from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ops.artifacts import ArtifactError, inventory, legacy_storage_key, sha256, storage_key, verify_bundle

ROOT = Path(__file__).resolve().parents[2]


class ArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = ROOT / ".tmp/ops"
        temporary.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def bundle(self) -> tuple[Path, str]:
        bundle = self.root / "bundle"
        model = bundle / "artifacts/ml_persona/model/metadata.json"
        model.parent.mkdir(parents=True)
        model.write_text('{"synthetic_test_fixture": true}', encoding="utf-8")
        dump = bundle / "database.dump"
        dump.write_bytes(b"synthetic pg dump fixture")
        manifest = {
            "schema_version": 1, "consistency": "writers-paused",
            "model_manifest_key": "artifacts/ml_persona/model/metadata.json", "model_manifest_sha256": sha256(model),
            "files": [
                {"key": "database.dump", "size": dump.stat().st_size, "sha256": sha256(dump)},
                *inventory(bundle / "artifacts", "artifacts", 1024),
            ],
            "lineage": {"schema_version": 1, "coverage": {"datasets": True, "persona_versions": True, "transcripts": True},
                        "unresolved_legacy_paths": [], "references": []},
        }
        manifest_path = bundle / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return bundle, sha256(manifest_path)

    def test_valid_bundle_verifies_without_loading_a_model_or_database(self) -> None:
        bundle, digest = self.bundle()
        self.assertEqual(verify_bundle(bundle, digest)["schema_version"], 1)

    def test_claimed_empty_coverage_without_database_inventory_is_rejected(self) -> None:
        bundle, digest = self.bundle()
        with self.assertRaisesRegex(ArtifactError, "database inventory"):
            verify_bundle(bundle, digest)

    def test_portable_keys_reject_traversal_windows_devices_and_ambiguous_names(self) -> None:
        for key in ("../dump", "/data/dump", "C:/data/dump", "data\\dump", "data//dump", "data/./dump", "data/NUL.txt", "data/name."):
            with self.subTest(key=key), self.assertRaises(ArtifactError):
                storage_key(key)

    def test_legacy_inventory_maps_windows_and_linux_roots_to_the_same_storage_key(self) -> None:
        expected = "data/uploads/source.csv"
        self.assertEqual(legacy_storage_key(r"E:\project\data\uploads\source.csv", r"E:\project\data", "data"), expected)
        self.assertEqual(legacy_storage_key("/app/data/uploads/source.csv", "/app/data", "data"), expected)
        with self.assertRaises(ArtifactError):
            legacy_storage_key(r"E:\other\source.csv", r"E:\project\data", "data")

    def test_corrupt_file_is_rejected(self) -> None:
        bundle, digest = self.bundle()
        (bundle / "database.dump").write_bytes(b"changed")
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, digest)

    def test_wrong_approved_manifest_digest_is_rejected(self) -> None:
        bundle, _digest = self.bundle()
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, "0" * 64)

    def test_unlisted_file_is_rejected(self) -> None:
        bundle, digest = self.bundle()
        (bundle / "extra").write_text("unexpected", encoding="utf-8")
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, digest)

    def test_size_budget_is_enforced(self) -> None:
        bundle, digest = self.bundle()
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, digest, max_bytes=1)

    def test_legacy_absolute_lineage_cannot_be_certified_as_portable(self) -> None:
        bundle, _digest = self.bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["lineage"]["unresolved_legacy_paths"] = [r"E:\project\data\old.csv"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, sha256(manifest_path))

    def test_missing_transcript_artifact_is_rejected(self) -> None:
        bundle, _digest = self.bundle()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["lineage"]["references"] = [{"kind": "transcript", "id": "test-conversation-v1", "storage_key": "data/missing.json", "sha256": "0" * 64}]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ArtifactError):
            verify_bundle(bundle, sha256(manifest_path))


if __name__ == "__main__":
    unittest.main()