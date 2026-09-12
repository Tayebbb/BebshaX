from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ops.artifacts import ArtifactError, sha256, verify_bundle
from scripts.ops.recovery import backup, database_target, new_output, restore, selected_target

ROOT = Path(__file__).resolve().parents[2]


class RecoverySafetyTests(unittest.TestCase):
    def test_no_writers_pause_consent_stops_before_any_database_access(self) -> None:
        with patch("scripts.ops.recovery.selected_target") as select, self.assertRaises(ArtifactError):
            backup(argparse.Namespace(writers_paused=False))
        select.assert_not_called()

    def test_restore_refuses_production_named_database_even_on_loopback(self) -> None:
        with self.assertRaises(ArtifactError):
            database_target("postgresql://test:test@127.0.0.1:5544/bebshax", "127.0.0.1:5544/bebshax", restore=True)

    def test_restore_requires_exact_target_confirmation(self) -> None:
        with self.assertRaises(ArtifactError):
            database_target("postgresql://test:test@127.0.0.1:5544/bebshax_rehearsal_test", "wrong", restore=True)

    def test_remote_restore_requires_separate_consent_and_verified_tls(self) -> None:
        url = "postgresql://test:test@database.example.test/bebshax_rehearsal_test?sslmode=verify-full"
        identity = "database.example.test:5432/bebshax_rehearsal_test"
        with self.assertRaises(ArtifactError):
            database_target(url, identity, restore=True)
        self.assertEqual(database_target(url, identity, restore=True, allow_remote=True).sslmode, "verify-full")
        with self.assertRaises(ArtifactError):
            database_target(url.replace("verify-full", "require"), identity, restore=True, allow_remote=True)

    def test_credentials_are_absent_from_target_repr_and_fingerprint(self) -> None:
        target = database_target("postgresql://test:not-a-real-password@127.0.0.1:5544/bebshax_rehearsal_test",
                                 "127.0.0.1:5544/bebshax_rehearsal_test", restore=True)
        self.assertNotIn("not-a-real-password", repr(target))
        self.assertNotIn("not-a-real-password", target.fingerprint)
        self.assertNotIn("BEBSHAX_DATABASE_URL", target.environment())

    def test_unselected_or_empty_url_never_uses_application_database(self) -> None:
        with patch.dict("os.environ", {"BEBSHAX_DATABASE_URL": "not-selected"}, clear=True), self.assertRaises(ArtifactError):
            selected_target(argparse.Namespace(target_url_env="BEBSHAX_RESTORE_TARGET_URL", confirm_target="unused"), restore=True)

    def test_output_cannot_overwrite_existing_work_or_nest_inside_source(self) -> None:
        parent = ROOT / ".tmp/ops"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            source = Path(directory) / "source"
            source.mkdir()
            with self.assertRaises(ArtifactError):
                new_output(source, [])
            with self.assertRaises(ArtifactError):
                new_output(source / "backup", [source])

    def test_backup_verify_and_restore_rehearsal_preserve_synthetic_files(self) -> None:
        parent = ROOT / ".tmp/ops"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            data = root / "data"
            artifacts = root / "artifacts"
            data.mkdir()
            metadata = artifacts / "ml_persona/model/metadata.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text('{"fixture": true}', encoding="utf-8")
            transcript = data / "transcript.json"
            transcript.write_text('{"synthetic": true, "version": 1}', encoding="utf-8")
            lineage = root / "lineage.json"
            lineage.write_text(json.dumps({
                "schema_version": 1, "coverage": {"datasets": True, "persona_versions": True, "transcripts": True},
                "unresolved_legacy_paths": [], "references": [{"kind": "transcript", "id": "fixture-v1",
                    "storage_key": "data/transcript.json", "sha256": sha256(transcript)}],
            }), encoding="utf-8")
            backup_args = argparse.Namespace(
                writers_paused=True, source_url_env="TEST_SOURCE_URL", confirm_source="127.0.0.1:5544/source",
                pg_bin=None, data_root=data, artifact_root=artifacts, max_bytes=1024**2,
                model_manifest_key="ml_persona/model/metadata.json", model_manifest_sha256=sha256(metadata),
                lineage_index=lineage, output=root / "bundle",
            )

            def postgres(tool, arguments, _target, _pg_bin):
                if tool == "pg_dump":
                    Path(arguments[arguments.index("--file") + 1]).write_bytes(b"synthetic-pg16-dump")
                return ""

            environment = {"TEST_SOURCE_URL": "postgresql://test:test@127.0.0.1:5544/source",
                           "TEST_TARGET_URL": "postgresql://test:test@127.0.0.1:5544/bebshax_rehearsal_test"}
            with patch.dict("os.environ", environment, clear=True), patch("scripts.ops.recovery.check_pg16"), \
                 patch("scripts.ops.recovery.scalar", side_effect=["revision_test", "1024"]), \
                 patch("scripts.ops.recovery.pg", side_effect=postgres):
                digest = backup(backup_args)
            verify_bundle(root / "bundle", digest)
            restore_args = argparse.Namespace(
                bundle=root / "bundle", manifest_sha256=digest, max_bytes=1024**2,
                target_url_env="TEST_TARGET_URL", confirm_target="127.0.0.1:5544/bebshax_rehearsal_test",
                allow_remote_target=False, pg_bin=None, output=root / "restored",
            )
            with patch.dict("os.environ", environment, clear=True), patch("scripts.ops.recovery.check_pg16"), \
                 patch("scripts.ops.recovery.scalar", side_effect=["0", "revision_test"]), \
                 patch("scripts.ops.recovery.pg", side_effect=postgres) as commands:
                self.assertEqual(restore(restore_args), digest)
            self.assertEqual((root / "restored/data/transcript.json").read_bytes(), transcript.read_bytes())
            self.assertEqual((root / "restored/artifacts/ml_persona/model/metadata.json").read_bytes(), metadata.read_bytes())
            restore_call = commands.call_args_list[0]
            self.assertEqual(restore_call.args[0], "pg_restore")
            self.assertIn("--single-transaction", restore_call.args[1])
            self.assertNotIn("--clean", restore_call.args[1])
            self.assertTrue((root / "restored/rehearsal.json").is_file())


if __name__ == "__main__":
    unittest.main()