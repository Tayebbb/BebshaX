import json
import unittest
from pathlib import Path

from scripts.ops.typecheck import BASELINE, ratchet

ROOT = Path(__file__).resolve().parents[2]


class TypecheckRatchetTests(unittest.TestCase):
    def report(self, errors: int) -> dict:
        diagnostics = [{"severity": "error", "file": "x.py", "range": {"start": {"line": 1, "character": 2}}, "message": "boom"}] * errors
        return {"summary": {"errorCount": errors, "warningCount": 1, "filesAnalyzed": 3}, "generalDiagnostics": diagnostics}

    def test_baseline_is_a_recorded_non_negative_integer_in_the_repository(self) -> None:
        self.assertEqual(BASELINE, ROOT / "deploy" / "pyright-baseline.json")
        recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertIsInstance(recorded["max_errors"], int)
        self.assertGreaterEqual(recorded["max_errors"], 0)

    def test_errors_at_or_below_the_baseline_pass_and_new_errors_fail(self) -> None:
        self.assertEqual(ratchet(self.report(3), 3), 0)
        self.assertEqual(ratchet(self.report(0), 3), 0)
        self.assertEqual(ratchet(self.report(4), 3), 1)


if __name__ == "__main__":
    unittest.main()
