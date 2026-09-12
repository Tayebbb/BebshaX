"""Offline API-image UID, filesystem and numerical-runtime probe; no settings or model load."""

from __future__ import annotations

import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path

FROZEN = {"numpy": "2.5.2", "scipy": "1.18.1", "scikit-learn": "1.9.0"}


def probe_runtime(
    writable: tuple[Path, ...] = (Path("/tmp"), Path("/app/data")),
    readonly: tuple[Path, ...] = (Path("/usr/local"), Path("/app/artifacts")),
) -> dict[str, object]:
    if getattr(os, "geteuid", lambda: None)() != 10001 or getattr(os, "getegid", lambda: None)() != 10001:
        raise ValueError("The API image must run as UID/GID 10001")
    versions = {name: importlib.metadata.version(name) for name in FROZEN}
    if versions != FROZEN:
        raise ValueError("The numerical runtime differs from the frozen artifact contract")
    for directory in readonly:
        if not directory.is_dir() or os.access(directory, os.W_OK):
            raise ValueError("Image code and artifact roots must exist and remain read-only")
    for directory in writable:
        with tempfile.TemporaryFile(dir=directory) as handle:
            handle.write(b"runtime-probe")
            handle.flush()
    return {"status": "PASS", "uid": 10001, "gid": 10001, "numerical_runtime": versions,
            "scope": "image identity, filesystem permissions and installed versions; not API/model/database readiness"}


def main() -> int:
    try:
        print(json.dumps(probe_runtime(), sort_keys=True))
        return 0
    except (OSError, ValueError, importlib.metadata.PackageNotFoundError) as error:
        print(f"Image runtime probe blocked: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())