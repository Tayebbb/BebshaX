"""Run the locked Pyright JS entry using existing Node, never download Node."""

from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path


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


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("Type checking blocked: the reviewed Node runtime is required", file=sys.stderr)
        return 1
    try:
        distribution = importlib.metadata.distribution("pyright")
        result = subprocess.run([node, str(entrypoint(distribution)), "--pythonpath", sys.executable, *sys.argv[1:]], check=False)
        return result.returncode
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        print("Type checking blocked: install the reviewed full lock before running this gate", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())