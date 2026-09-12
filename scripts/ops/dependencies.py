"""Resolve and install the reviewed Python 3.12 release dependency graph."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FULL_LOCK = ROOT / "apps/backend/requirements.lock"
RUNTIME_LOCK = ROOT / "deploy/python/runtime.lock"
BASELINE = ROOT / "deploy/python/baseline.constraints"
MODEL_CONSTRAINTS = ROOT / "ml_persona/constraints.txt"
FROZEN = {"numpy": "2.5.2", "scipy": "1.18.1", "scikit-learn": "1.9.0"}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def require_python() -> None:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Release tooling requires Python 3.12; no automatic interpreter install")


def run(arguments: list[str]) -> None:
    environment = {**os.environ, "PIP_CONFIG_FILE": os.devnull, "UV_NO_CONFIG": "1", "UV_PYTHON_DOWNLOADS": "never"}
    subprocess.run(arguments, cwd=ROOT, env=environment, check=True)


def snapshot() -> None:
    require_python()
    versions = {
        normalize(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }
    for name, version in FROZEN.items():
        if versions.get(name) != version:
            raise ValueError(f"Frozen numerical runtime mismatch: {name}")
    if BASELINE.exists():
        raise ValueError("Baseline already exists; review and remove it explicitly before recapturing")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    excluded = {"bebshax", "bebshax-persona-ml"}
    BASELINE.write_text(
        "# Resolver constraints from the reviewed Python 3.12 environment; not an install list.\n"
        + "\n".join(f"{name}=={version}" for name, version in sorted(versions.items()) if name not in excluded)
        + "\n",
        encoding="utf-8",
    )
    print(f"Captured {len(versions) - len(excluded)} baseline constraints; frozen model runtime matches")


def lock() -> None:
    require_python()
    if not BASELINE.is_file():
        raise ValueError("Capture and review the baseline constraints first")
    common = [
        "uv", "pip", "compile", "--universal", "--python", sys.executable,
        "--python-version", "3.12", "--generate-hashes", "--no-header", "--no-annotate",
        "--no-emit-index-url", "--index-url", "https://pypi.org/simple",
        "--constraint", str(MODEL_CONSTRAINTS),
    ]
    manifests = [str(ROOT / "apps/backend/pyproject.toml"), str(ROOT / "ml_persona/pyproject.toml")]
    run([*common, "--constraint", str(BASELINE), "--extra", "dev", "--output-file", str(FULL_LOCK), *manifests])
    run([*common, "--constraint", str(FULL_LOCK), "--output-file", str(RUNTIME_LOCK), *manifests])
    check()


def locked_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for entry in path.read_text(encoding="utf-8").replace("\\\n", " ").splitlines():
        if not entry.strip() or entry.startswith("#"):
            continue
        matched = re.match(r"([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)", entry)
        if matched is None or not re.search(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)", entry):
            raise ValueError(f"Unpinned or unhashed dependency in {path.name}")
        name, version = normalize(matched[1]), matched[2]
        if name in versions and versions[name] != version:
            raise ValueError(f"Multiple versions require a new platform review: {name}")
        versions[name] = version
    return versions


def check() -> None:
    full = locked_versions(FULL_LOCK)
    runtime = locked_versions(RUNTIME_LOCK)
    for name, version in FROZEN.items():
        if full.get(name) != version or runtime.get(name) != version:
            raise ValueError(f"Frozen numerical lock mismatch: {name}")
    for name, version in runtime.items():
        if full.get(name) != version:
            raise ValueError(f"Runtime/full lock drift: {name}")
    for relative in ("apps/backend/pyproject.toml", "ml_persona/pyproject.toml"):
        project = tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))["project"]
        for requirement in project["dependencies"]:
            name = normalize(re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0])
            if name not in runtime:
                raise ValueError(f"Missing declared runtime dependency: {name}")
        for requirement in project.get("optional-dependencies", {}).get("dev", []):
            name = normalize(re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0])
            if name not in full:
                raise ValueError(f"Missing declared dev dependency: {name}")
    print(f"PASS: {len(full)} full / {len(runtime)} runtime locked distributions; frozen model pins match")


def install(wheelhouse: Path | None, runtime_only: bool) -> None:
    require_python()
    check()
    index = ["--no-index", "--find-links", str(wheelhouse)] if wheelhouse else ["--index-url", "https://pypi.org/simple"]
    selected = RUNTIME_LOCK if runtime_only else FULL_LOCK
    run([sys.executable, "-m", "pip", "--isolated", "install", "--require-hashes", "--only-binary=:all:",
         "--constraint", str(MODEL_CONSTRAINTS), "--requirement", str(selected), *index])
    if not runtime_only:
        run([sys.executable, "-m", "pip", "--isolated", "install", "--no-deps", "--no-build-isolation",
             "--no-index", "-e", str(ROOT / "ml_persona"), "-e", f"{ROOT / 'apps/backend'}[dev]"])
    run([sys.executable, "-m", "pip", "--isolated", "check"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("snapshot", "lock", "check", "install"))
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--runtime-only", action="store_true")
    arguments = parser.parse_args()
    try:
        if arguments.operation == "snapshot":
            snapshot()
        elif arguments.operation == "lock":
            lock()
        elif arguments.operation == "check":
            check()
        else:
            install(arguments.wheelhouse, arguments.runtime_only)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Dependency gate failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())