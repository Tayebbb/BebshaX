#!/usr/bin/env python3
"""One-shot fresh-machine setup for BebshaX (docs/SETUP.md steps 2-6).

Run with the SYSTEM python from the repo root:

    python scripts/setup.py [--profile minimal] [--skip-docker] [--skip-datasets] [--skip-frontend]

Installs the reviewed dependency graph. Database changes and dataset preparation
require explicit options. Never reads or writes an environment/credential file.
"""

from __future__ import annotations

import argparse
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
    if sys.version_info[:2] != (3, 12):
        sys.exit(f"The frozen release requires Python 3.12, found {sys.version.split()[0]}")
    print(f"OK: {sys.version.split()[0]}")


def ensure_venv() -> None:
    step("Virtual environment (.venv)")
    if VENV_PY.exists():
        print("OK: .venv already exists")
        return
    run([sys.executable, "-m", "venv", str(VENV)])


def install_backend() -> None:
    step("Backend install (reviewed hash lock + local packages)")
    run([VENV_PY, str(ROOT / "scripts" / "ops" / "dependencies.py"), "install"])


def report_configuration() -> None:
    step("Operator configuration")
    print("Supply BEBSHAX_DATABASE_URL and BEBSHAX_JWT_SECRET explicitly before starting the API.")
    print("No credential files are read, created, copied, or rotated by this helper.")


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


def run_migrations(url_env: str, confirmation: str, allow_remote: bool) -> None:
    step("Migrations (alembic upgrade head)")
    command = [VENV_PY, str(ROOT / "scripts/migrate_db.py"), "--url-env", url_env,
               "--confirm-target", confirmation, "--apply"]
    if allow_remote:
        command.append("--allow-remote-target")
    rc = run(command, check=False)
    if rc != 0:
        sys.exit("Migration gate failed; verify the explicitly selected direct target and approvals")


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
        print("npm not found - the reviewed release uses Node.js 24.20.0 and npm 11.19.0")
        return
    run([npm, "ci", "--workspaces", "--include-workspace-root"], cwd=ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=None, help="explicit reviewed dataset profile; omitted means no dataset work")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--skip-datasets", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--start-database", action="store_true")
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--migration-url-env")
    parser.add_argument("--confirm-migration-target")
    parser.add_argument("--allow-remote-migration", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.migrate and not (args.migration_url_env and args.confirm_migration_target):
        parser.error("--migrate requires --migration-url-env and --confirm-migration-target before setup runs")
    ensure_python_version()
    ensure_venv()
    install_backend()
    report_configuration()
    if args.start_database and not args.skip_docker:
        start_database(False)
    if args.migrate:
        run_migrations(args.migration_url_env, args.confirm_migration_target, args.allow_remote_migration)
    if args.profile is not None and not args.skip_datasets:
        setup_datasets(args.profile, False)
    install_frontend(args.skip_frontend)
    if args.verify:
        run_tests()

    step("Done")
    print("Start everything:  node scripts/dev.js")
    print("API health:        http://localhost:8000/api/health")
    print("Frontend:          http://localhost:5173")
    print("Release prerequisites: docs/SETUP.md (remote inference requires connectivity and quota)")


if __name__ == "__main__":
    main()
