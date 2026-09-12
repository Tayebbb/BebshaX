import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy.runtime_probe import FROZEN, probe_runtime


class ImageRuntimeProbeTests(unittest.TestCase):
    def test_non_root_image_with_frozen_versions_checks_real_writes_without_leaving_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, \
                patch("deploy.runtime_probe.os.geteuid", return_value=10001, create=True), \
                patch("deploy.runtime_probe.os.getegid", return_value=10001, create=True), \
                patch("deploy.runtime_probe.importlib.metadata.version", side_effect=FROZEN.__getitem__), \
                patch("deploy.runtime_probe.os.access", return_value=False):
            directory = Path(temporary)
            result = probe_runtime((directory,), (directory,))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(list(directory.iterdir()), [])
            self.assertIn("not API/model/database readiness", result["scope"])

    def test_root_or_wrong_group_fails_before_any_filesystem_write(self) -> None:
        for uid, gid in ((0, 0), (10001, 0), (1000, 10001)):
            with self.subTest(uid=uid, gid=gid), \
                    patch("deploy.runtime_probe.os.geteuid", return_value=uid, create=True), \
                    patch("deploy.runtime_probe.os.getegid", return_value=gid, create=True), \
                    patch("deploy.runtime_probe.tempfile.TemporaryFile") as writer, self.assertRaises(ValueError):
                probe_runtime()
            writer.assert_not_called()

    def test_runtime_drift_or_writable_code_fails_before_any_probe_write(self) -> None:
        for drift, writable in ((True, False), (False, True)):
            versions = {**FROZEN, **({"numpy": "0.0.0"} if drift else {})}
            with self.subTest(drift=drift, writable=writable), tempfile.TemporaryDirectory() as temporary, \
                    patch("deploy.runtime_probe.os.geteuid", return_value=10001, create=True), \
                    patch("deploy.runtime_probe.os.getegid", return_value=10001, create=True), \
                    patch("deploy.runtime_probe.importlib.metadata.version", side_effect=versions.__getitem__), \
                    patch("deploy.runtime_probe.os.access", return_value=writable), \
                    patch("deploy.runtime_probe.tempfile.TemporaryFile") as writer, self.assertRaises(ValueError):
                probe_runtime((Path(temporary),), (Path(temporary),))
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()