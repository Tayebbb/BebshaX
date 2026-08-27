#!/usr/bin/env python3
"""One-shot fresh-machine setup for BebshaX (docs/SETUP.md steps 2-6).

Run with the SYSTEM python from the repo root:

    python scripts/setup.py [--profile minimal] [--skip-docker] [--skip-datasets] [--skip-frontend]

Idempotent: every step detects "already done" and skips. Fails loudly on the
first hard error; never writes secrets anywhere except the local .env.
"""

from __future__ import annotations

import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
IS_WINDOWS = sys.platform == "win32"
VENV_BIN = VENV / ("Scripts" if IS_WINDOWS else "bin")
VENV_PY = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")


def step(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def run(cmd: list[str | Path], cwd: Path = ROOT, check: bool = True) -> int:
    printable = " ".join(str(c) for c in cmd)
    print(f"$ {printable}")
    return subprocess.run([str(c) for c in cmd], cwd=cwd, check=check).returncode


def ensure_python_version() -> None:
    step("Python version")
    if sys.version_info < (3, 12):
        sys.exit(f"Python 3.12+ required, found {sys.version.split()[0]}")
    print(f"OK: {sys.version.split()[0]}")


def ensure_venv() -> None:
    step("Virtual environment (.venv)")
    if VENV_PY.exists():
        print("OK: .venv already exists")
        return
    run([sys.executable, "-m", "venv", str(VENV)])


def install_backend() -> None:
    step("Backend install (editable + dev extras)")
    run([VENV_PY, "-m", "pip", "install", "-e", str(ROOT / "apps" / "backend") + "[dev]"])


def ensure_env_file() -> None:
    step("Secrets (.env)")
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_path.exists():
        if not example.exists():
            sys.exit(".env.example missing - cannot bootstrap .env")
        shutil.copyfile(example, env_path)
        print("Created .env from .env.example")
    text = env_path.read_text(encoding="utf-8")
    needs_secret = True
    for line in text.splitlines():
        if line.startswith("BEBSHAX_JWT_SECRET="):
            value = line.split("=", 1)[1].strip()
            # only replace the shipped placeholder or a too-short value —
            # never silently rotate a legitimate secret
            needs_secret = len(value) < 32 or value.startswith("<")
            break
    if needs_secret:
        token = secrets.token_urlsafe(48)
        lines = []
        replaced = False
        for line in text.splitlines():
            if line.startswith("BEBSHAX_JWT_SECRET="):
                lines.append(f"BEBSHAX_JWT_SECRET={token}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"BEBSHAX_JWT_SECRET={token}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Generated a fresh BEBSHAX_JWT_SECRET (local .env only)")
    else:
        print("OK: BEBSHAX_JWT_SECRET already set")


def start_database(skip_docker: bool) -> None:
    step("Database (docker compose service 'db', pgvector on :5433)")
    if skip_docker:
        print("Skipped (--skip-docker) - set BEBSHAX_DATABASE_URL to your own Postgres")
        return
    if shutil.which("docker") is None:
        print("Docker not found - skipping. Point BEBSHAX_DATABASE_URL at a pgvector Postgres instead.")
        return
    # --wait blocks on the compose healthcheck (pg_isready) — no sleep guessing
    rc = run(["docker", "compose", "up", "-d", "--wait", "db"], check=False)
    if rc != 0:
        print("docker compose failed (daemon down?) - configure BEBSHAX_DATABASE_URL manually.")
        return


def run_migrations() -> None:
    step("Migrations (alembic upgrade head)")
    rc = run([VENV_PY, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "apps" / "backend", check=False)
    if rc != 0:
        sys.exit("alembic upgrade failed - check BEBSHAX_DATABASE_URL / database availability")


def setup_datasets(profile: str, skip: bool) -> None:
    step(f"Datasets (profile: {profile})")
    if skip:
        print("Skipped (--skip-datasets)")
        return
    rc = run([VENV_PY, str(ROOT / "scripts" / "setup_datasets.py"), "--profile", profile], check=False)
    if rc != 0:
        print("Dataset setup reported failures - see output above (optional datasets may soft-fail).")


def run_tests() -> None:
    step("Verification (backend test suite)")
    rc = run([VENV_PY, "-m", "pytest", "apps/backend/tests", "-q"], check=False)
    if rc != 0:
        sys.exit("Test suite not green - setup is incomplete")


def install_frontend(skip: bool) -> None:
    step("Frontend install (npm)")
    if skip:
        print("Skipped (--skip-frontend)")
        return
    npm = shutil.which("npm")
    if npm is None:
        print("npm not found - install Node.js 20+ to run the frontend")
        return
    run([npm, "ci"], cwd=ROOT / "apps" / "frontend")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="minimal", help="dataset profile (minimal/development/evaluation/full)")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--skip-datasets", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    args = parser.parse_args()

    ensure_python_version()
    ensure_venv()
    install_backend()
    ensure_env_file()
    start_database(args.skip_docker)
    run_migrations()
    setup_datasets(args.profile, args.skip_datasets)
    install_frontend(args.skip_frontend)
    run_tests()

    step("Done")
    print("Start everything:  node scripts/dev.js")
    print("API health:        http://localhost:8000/api/health")
    print("Frontend:          http://localhost:5173")
    print("Demo mode & offline drill: docs/DEMO.md")


if __name__ == "__main__":
    main()
