"""Clean offline installation from an explicit reviewed platform wheelhouse."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env={**os.environ, "PIP_CONFIG_FILE": os.devnull})


def reproduce(environment: Path, wheelhouse: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Python 3.12 is required")
    environment, wheelhouse = environment.resolve(), wheelhouse.resolve()
    if not environment.is_relative_to(ROOT / ".tmp/ops") or environment.exists() or not wheelhouse.is_dir():
        raise ValueError("Use a new environment under .tmp/ops and an existing explicit wheelhouse")
    run([sys.executable, "-m", "venv", str(environment)])
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([str(python), "-m", "pip", "--isolated", "install", "--no-index", "--find-links", str(wheelhouse),
         "--require-hashes", "--only-binary=:all:", "-c", str(ROOT / "ml_persona/constraints.txt"),
         "-r", str(ROOT / "apps/backend/requirements.lock")])
    with tempfile.TemporaryDirectory(prefix="release-source-", dir=environment.parent) as directory:
        copied = Path(directory)
        for name, source, source_directory in (("backend", ROOT / "apps/backend", "bebshax"), ("ml_persona", ROOT / "ml_persona", "src")):
            target = copied / name
            target.mkdir()
            shutil.copy2(source / "pyproject.toml", target / "pyproject.toml")
            shutil.copytree(source / source_directory, target / source_directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*"))
        wheels = copied / "wheels"
        run([str(python), "-m", "pip", "--isolated", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
             "--wheel-dir", str(wheels), str(copied / "ml_persona"), str(copied / "backend")])
        run([str(python), "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
             *(str(wheel) for wheel in sorted(wheels.glob("*.whl")))])
    run([str(python), "-m", "pip", "--isolated", "check"])
    print("PASS: clean offline dependency and local-wheel installation; shared environment untouched")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        reproduce(arguments.environment, arguments.wheelhouse)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Offline installation blocked: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())