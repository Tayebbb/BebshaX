import runpy
import unittest
from pathlib import Path


class RetiredCommandTests(unittest.TestCase):
    def test_historical_commands_exit_without_importing_application_or_providers(self) -> None:
        scripts = Path(__file__).resolve().parents[1]
        for name in ("benchmark_ollama.py", "smoke_ollama.py", "demo_preflight.py", "judge_local_interview.py"):
            with self.subTest(script=name), self.assertRaisesRegex(SystemExit, "retired"):
                runpy.run_path(str(scripts / name), run_name="__main__")


if __name__ == "__main__":
    unittest.main()