"""Run the locked Pyright JS entry using existing Node, never download Node.

The gate is a ratchet: the count of type errors may only go down. The recorded
maximum lives in deploy/pyright-baseline.json; lower it as debt is repaid.
"""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[2] / "deploy" / "pyright-baseline.json"


def entrypoint(distribution: importlib.metadata.Distribution) -> Path:
    for entry in distribution.files or []:
        if entry.name != "package.json":
            continue
        manifest = Path(distribution.locate_file(entry))
        package = json.loads(manifest.read_text(encoding="utf-8"))
        if package.get("name") != "pyright":
            continue
        executable = package.get("bin", {}).get("pyright")
        if not isinstance(executable, str):
            raise ValueError("Missing published Pyright CLI")
        candidate = (manifest.parent / executable).resolve()
        if not candidate.is_relative_to(manifest.parent.resolve()) or not candidate.is_file():
            raise ValueError("Invalid published Pyright CLI")
        return candidate
    raise ValueError("No published Pyright package entrypoint")


def ratchet(report: dict, max_errors: int) -> int:
    """0 when the error count stays within the recorded baseline, else 1."""
    summary = report.get("summary", {})
    errors = int(summary.get("errorCount", 0))
    for diagnostic in report.get("generalDiagnostics", []):
        if diagnostic.get("severity") != "error":
            continue
        start = diagnostic.get("range", {}).get("start", {})
        print(f"{diagnostic.get('file')}:{start.get('line', 0) + 1}:{start.get('character', 0) + 1} - {diagnostic.get('message', '').splitlines()[0]}")
    print(f"Pyright: {errors} errors (baseline {max_errors}), {summary.get('warningCount', 0)} warnings, {summary.get('filesAnalyzed', 0)} files")
    if errors > max_errors:
        print(f"Type checking blocked: {errors - max_errors} new type error(s) above the recorded baseline", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("Type checking blocked: the reviewed Node runtime is required", file=sys.stderr)
        return 1
    try:
        max_errors = int(json.loads(BASELINE.read_text(encoding="utf-8"))["max_errors"])
        distribution = importlib.metadata.distribution("pyright")
        arguments = [argument for argument in sys.argv[1:] if argument != "--outputjson"]
        result = subprocess.run(
            [node, str(entrypoint(distribution)), "--pythonpath", sys.executable, "--outputjson", *arguments],
            check=False, capture_output=True, text=True, encoding="utf-8",
        )
        if not result.stdout.strip():
            sys.stderr.write(result.stderr)
            return result.returncode or 1
        return ratchet(json.loads(result.stdout), max_errors)
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError, KeyError):
        print("Type checking blocked: install the reviewed full lock before running this gate", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())