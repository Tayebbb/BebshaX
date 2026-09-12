"""Parse both Compose profiles using disposable configuration, never .env."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standalone", action="store_true", help="Use an already installed docker-compose executable")
    arguments = parser.parse_args()
    compose = ["docker-compose"] if arguments.standalone else ["docker", "compose"]
    allowed = {"PATH", "Path", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "HOME", "USERPROFILE", "TMP", "TEMP",
               "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData", "ALLUSERSPROFILE"}
    environment = {name: value for name, value in os.environ.items() if name in allowed}
    environment.update({
        "COMPOSE_DISABLE_ENV_FILE": "1",
        "DOCKER_CONFIG": str(ROOT / ".tmp/ops/docker-config"),
        "BEBSHAX_POSTGRES_PASSWORD": "ops-validation-not-a-real-password",
        "BEBSHAX_DATABASE_URL": "postgresql+asyncpg://validation:validation@db:5432/validation",
        "BEBSHAX_JWT_SECRET": "ops-validation-not-a-real-signing-secret",
        "BEBSHAX_FRONTEND_BASE_URL": "https://frontend.example.test",
        "BEBSHAX_ML_PERSONA_MANIFEST_SHA256": "0" * 64,
    })
    temporary_root = ROOT / ".tmp/ops"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compose-", dir=temporary_root) as directory:
        empty = Path(directory) / "empty"
        empty.touch()
        for profile in ([], ["--profile", "full"]):
            result = subprocess.run(
                [*compose, "--env-file", str(empty), "-f", str(ROOT / "docker-compose.yml"), *profile, "config", "--quiet"],
                cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=30,
            )
            if result.returncode:
                print(f"FAIL: Compose {'full' if profile else 'default'} parse (exit {result.returncode})")
                print(result.stderr[:2000])
                return result.returncode
    print("PASS: default and full Compose profiles; no environment file, database or service started")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())