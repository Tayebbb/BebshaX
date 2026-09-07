"""Demo-day preflight gate (docs/DEMO.md §6).

Verifies the machine is actually ready for the OFFLINE exhibition demo:
env points at the local pgvector container, demo mode is on, the container
is healthy, migrations are at head, the demo seed exists, grounding datasets
are present, and Ollama can serve the local fallback pool. With
--strict-offline it also scans for cloud reliance (key names, remote *_URL
hosts, and a Neon tenant URL baked into apps/frontend/dist). Exits 1 on any
✗ so it can gate scripts.

Run from the repo root:
    .\\.venv\\Scripts\\python scripts\\demo_preflight.py [--strict-offline]

Uses stdlib + the backend's own deps only (sqlalchemy/alembic via the
installed `bebshax` package). Never prints secret values — for the DB URL
only host:port is shown; for API-key scans only variable NAMES are shown.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
ENV_FILE = REPO_ROOT / ".env"
FRONTEND_DIST = REPO_ROOT / "apps" / "frontend" / "dist"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1"}
LOCAL_DB_PORT = 5433
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
BACKEND_HEALTH_URL = "http://localhost:8000/api/health"
REQUIRED_OLLAMA_MODEL = "llama3.2:3b"
OPTIONAL_OLLAMA_MODELS = ("qwen3:4b", "nomic-embed-text")
DEMO_SEED_EMAIL = "founder@bebshax.ai"
# Matches names like BEBSHAX_STRIPE_SECRET_KEY / FOO_API_KEY / X_ACCESS_KEY / *_API_TOKEN.
CLOUD_KEY_NAME_RE = re.compile(r"(API_KEY|SECRET_KEY|ACCESS_KEY|API_TOKEN)$")
# Endpoint-style names whose host should be local for an offline demo.
URL_NAME_RE = re.compile(r"_URL$")
JWT_MIN_LEN = 32
# A Neon Auth tenant URL inlined into the SPA build means the "Continue with
# Google" button is LIVE at the venue — and dead without internet.
CLOUD_TENANT_MARKERS = ("neonauth", "neon.tech")
DIST_SCAN_SUFFIXES = {".js", ".html", ".css"}

_failures: list[str] = []


def ok(label: str, detail: str = "") -> None:
    print(f"  \u2713 {label}" + (f" — {detail}" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    print(f"  \u26a0 {label}" + (f" — {detail}" if detail else ""))


def fail(label: str, hint: str) -> None:
    _failures.append(label)
    print(f"  \u2717 {label}")
    print(f"      fix: {hint}")


def skip(label: str, detail: str) -> None:
    print(f"  \u2013 {label} — {detail}")


def parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser. Values are kept in memory only, never printed."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("'\"")
        values[key.strip()] = value
    return values


def effective(name: str, dotenv: dict[str, str]) -> str | None:
    """Same precedence the backend sees: real environment beats .env."""
    return os.environ.get(name) or dotenv.get(name) or None


def config_default_database_url() -> str:
    from bebshax.config import Settings  # class import only — does not validate jwt

    return Settings.model_fields["database_url"].default


# ── 1-3. .env / DATABASE_URL / DEMO_MODE ────────────────────────────────────

def check_env_file(dotenv: dict[str, str]) -> str | None:
    """Returns the resolved database URL (never printed in full)."""
    if not ENV_FILE.exists():
        fail(".env exists at repo root", "copy .env.demo to .env (backup any existing .env first)")
    else:
        ok(".env exists at repo root")

    db_url = effective("BEBSHAX_DATABASE_URL", dotenv)
    if db_url is None:
        db_url = config_default_database_url()
        note = "unset — backend default applies"
    else:
        note = ""

    parsed = urlparse(db_url)
    host = (parsed.hostname or "?").lower()
    port = parsed.port or (5432 if host != "?" else None)
    endpoint = f"{host}:{port}"
    if host in LOCAL_DB_HOSTS and port == LOCAL_DB_PORT:
        ok(f"BEBSHAX_DATABASE_URL targets {endpoint}", note)
    else:
        fail(
            f"BEBSHAX_DATABASE_URL targets {endpoint} (need localhost:{LOCAL_DB_PORT})",
            "offline demo must use the local pgvector container — copy .env.demo over .env",
        )

    demo_mode = (effective("BEBSHAX_DEMO_MODE", dotenv) or "").lower()
    if demo_mode in ("true", "1", "yes", "on"):
        ok("BEBSHAX_DEMO_MODE=true")
    else:
        fail(
            f"BEBSHAX_DEMO_MODE={demo_mode or '<unset>'} (need true)",
            "set BEBSHAX_DEMO_MODE=true in .env so the demo seed and cached labels work",
        )
    return db_url


def check_jwt_secret(dotenv: dict[str, str]) -> None:
    """Validate BEBSHAX_JWT_SECRET without ever printing its value."""
    hint = (
        "set a strong value in .env — generate one: "
        '.venv\\Scripts\\python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
    secret = effective("BEBSHAX_JWT_SECRET", dotenv)
    if not secret:
        fail("BEBSHAX_JWT_SECRET is missing (backend will refuse to start)", hint)
    elif "CHANGE-ME" in secret.upper():
        fail("BEBSHAX_JWT_SECRET is a CHANGE-ME placeholder", hint)
    elif len(secret) < JWT_MIN_LEN:
        fail(f"BEBSHAX_JWT_SECRET too short ({len(secret)} chars, need ≥{JWT_MIN_LEN})", hint)
    else:
        ok("BEBSHAX_JWT_SECRET set", f"{len(secret)} chars")


# ── 4. Docker container health ──────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str] | None:
    try:
        # check=False: callers inspect returncode themselves (docker may be down).
        return subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_docker_db() -> None:
    proc = _run(["docker", "compose", "ps", "--format", "json", "db"])
    state = health = None
    if proc is not None and proc.returncode == 0 and proc.stdout.strip():
        entries: list[dict] = []
        try:
            loaded = json.loads(proc.stdout)
            entries = loaded if isinstance(loaded, list) else [loaded]
        except json.JSONDecodeError:  # NDJSON variant of compose ps
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        for entry in entries:
            if entry.get("Service") == "db" or entry.get("Name") == "bebshax-db":
                state = entry.get("State")
                health = entry.get("Health")
                break
    if state is None:  # compose gave nothing — ask the engine directly
        proc = _run(
            ["docker", "inspect", "-f", "{{.State.Status}}|{{.State.Health.Status}}", "bebshax-db"]
        )
        if proc is not None and proc.returncode == 0:
            parts = proc.stdout.strip().split("|")
            state = parts[0] or None
            health = parts[1] if len(parts) > 1 else None

    if state == "running" and (health in (None, "", "healthy")):
        ok("docker db container up + healthy", f"state={state}, health={health or 'n/a'}")
    elif state is None:
        fail(
            "docker db container not found (bebshax-db)",
            "start Docker Desktop, then: docker compose up -d --wait db",
        )
    else:
        fail(
            f"docker db container state={state}, health={health or 'unknown'}",
            "docker compose up -d --wait db  (waits for pg_isready healthcheck)",
        )


# ── 5-6. Alembic head + demo seed (backend's own engine) ────────────────────

async def _db_checks(db_url: str) -> None:
    import sqlalchemy as sa
    from alembic.config import Config as AlembicConfig
    from alembic.script import ScriptDirectory
    from bebshax.db.engine import normalize_async_database_url
    from sqlalchemy.ext.asyncio import create_async_engine

    heads = set(
        ScriptDirectory.from_config(
            AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
        ).get_heads()
    )

    engine = create_async_engine(normalize_async_database_url(db_url))
    try:
        async with engine.connect() as conn:
            try:
                current = set(
                    (await conn.execute(sa.text("SELECT version_num FROM alembic_version")))
                    .scalars()
                    .all()
                )
            except SQLAlchemyError:  # table missing = no migrations applied yet
                current = set()
            if current == heads:
                ok("alembic current == head", ", ".join(sorted(heads)))
            else:
                fail(
                    f"alembic current={sorted(current) or 'none'} != head={sorted(heads)}",
                    "cd apps/backend; ..\\..\\.venv\\Scripts\\python -m alembic upgrade head",
                )

            try:
                users = (
                    await conn.execute(
                        sa.text("SELECT count(*) FROM users WHERE email = :e"),
                        {"e": DEMO_SEED_EMAIL},
                    )
                ).scalar_one()
                personas = (
                    await conn.execute(sa.text("SELECT count(*) FROM personas"))
                ).scalar_one()
                if users > 0 or personas > 0:
                    ok(
                        "demo seed present",
                        f"{DEMO_SEED_EMAIL} user={'yes' if users else 'no'}, personas={personas}",
                    )
                else:
                    fail(
                        "demo seed missing (no demo user, no personas)",
                        "start the backend once with BEBSHAX_DEMO_MODE=true — seeding runs at startup",
                    )
            except SQLAlchemyError as exc:
                fail(
                    f"demo seed query failed ({type(exc).__name__})",
                    "run migrations first: alembic upgrade head from apps/backend",
                )
    finally:
        await engine.dispose()


def check_database(db_url: str) -> None:
    try:
        asyncio.run(asyncio.wait_for(_db_checks(db_url), timeout=15))
    except (asyncio.TimeoutError, TimeoutError):
        fail(
            "database unreachable (15s timeout)",
            "docker compose up -d --wait db — and check BEBSHAX_DATABASE_URL points at localhost:5433",
        )
    except (SQLAlchemyError, OSError, ValueError) as exc:  # refused / bad URL / driver
        fail(
            f"database checks failed ({type(exc).__name__})",
            "docker compose up -d --wait db, then alembic upgrade head from apps/backend",
        )
    except ImportError as exc:
        fail(
            f"backend package not importable ({exc.name or 'bebshax'})",
            '.venv\\Scripts\\pip install -e "apps/backend[dev]"',
        )


# ── 7. Grounding datasets ────────────────────────────────────────────────────

def check_processed_datasets() -> None:
    """EvidenceStore reads data/processed/*.jsonl; empty = zero OBSERVED claims."""
    files = sorted(PROCESSED_DIR.glob("*.jsonl")) if PROCESSED_DIR.is_dir() else []
    if files:
        ok("data/processed has grounding datasets", f"{len(files)} jsonl file(s)")
    else:
        fail(
            "data/processed has no *.jsonl — persona evidence grounding would be empty",
            ".venv\\Scripts\\python scripts\\setup_datasets.py --profile minimal  (needs internet once)",
        )


# ── 8. Ollama ────────────────────────────────────────────────────────────────

def _http_json(url: str, timeout: float) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # localhost only
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def check_ollama() -> None:
    data = _http_json(OLLAMA_TAGS_URL, timeout=3)
    if data is None:
        fail(
            "Ollama daemon not reachable on localhost:11434",
            "run `ollama serve` (Ollama is the offline fallback pool — required at the venue)",
        )
        return
    names = [m.get("name", "") for m in data.get("models", [])]
    ok("Ollama daemon reachable", f"{len(names)} model(s) installed")

    if any(n == REQUIRED_OLLAMA_MODEL or n.startswith(REQUIRED_OLLAMA_MODEL) for n in names):
        ok(f"model {REQUIRED_OLLAMA_MODEL} present (primary local pool)")
    else:
        fail(
            f"model {REQUIRED_OLLAMA_MODEL} missing",
            f"ollama pull {REQUIRED_OLLAMA_MODEL}  (do this BEFORE demo day — needs internet)",
        )

    for model in OPTIONAL_OLLAMA_MODELS:
        base = model.split(":")[0]
        if any(n == model or n.split(":")[0] == base for n in names):
            ok(f"model {model} present")
        else:
            warn(f"model {model} missing (optional)", f"ollama pull {model} for extra headroom")


# ── 9. Running backend sanity ────────────────────────────────────────────────

def check_backend_health() -> None:
    data = _http_json(BACKEND_HEALTH_URL, timeout=2)
    if data is None:
        skip("backend on :8000", "not running — skipped (start with: node scripts/dev.js)")
        return
    if data.get("demo_mode") is True:
        ok("running backend reports demo_mode=true")
    else:
        fail(
            f"running backend reports demo_mode={data.get('demo_mode')!r}",
            "backend was started before .env flipped — restart it after fixing .env",
        )


# ── 10. --strict-offline: cloud-reliance scans (names + hosts only) ─────────

def check_dist_offline() -> None:
    """A built SPA carrying a Neon tenant URL would show a live Google button.

    Vite inlines VITE_NEON_AUTH_URL at BUILD time, so a dist produced before
    .env.demo was copied over .env keeps the cloud tenant no matter what the
    running .env says. Only file paths are printed, never the URL.
    """
    if not FRONTEND_DIST.is_dir():
        skip(
            "apps/frontend/dist cloud-tenant scan",
            "no build present (the Vite dev server reads .env live — nothing baked)",
        )
        return
    hits: list[str] = []
    for path in sorted(FRONTEND_DIST.rglob("*")):
        if path.suffix not in DIST_SCAN_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in CLOUD_TENANT_MARKERS):
            hits.append(path.relative_to(REPO_ROOT).as_posix())
    if hits:
        fail(
            f"apps/frontend/dist embeds a Neon tenant URL in {len(hits)} file(s): "
            + ", ".join(hits[:3])
            + (" …" if len(hits) > 3 else ""),
            "copy .env.demo over .env FIRST, then rebuild: cd apps/frontend; npm run build "
            "(compose users: docker compose --profile full build web)",
        )
    else:
        ok("apps/frontend/dist has no baked cloud tenant URL")


def check_strict_offline(dotenv: dict[str, str]) -> None:
    candidates = set(dotenv) | {k for k in os.environ if k.startswith("BEBSHAX_")}
    flagged = sorted(
        k for k in candidates if CLOUD_KEY_NAME_RE.search(k) and effective(k, dotenv)
    )
    if flagged:
        warn(
            "cloud-style API keys are set (names only)",
            ", ".join(flagged) + " — fine if intentional, but the venue has NO internet",
        )
    else:
        ok("no cloud-style *_API_KEY variables set")

    # *_URL / *_BASE_URL / *_AUTH_URL vars pointing at non-local hosts imply
    # cloud reliance. Print name + host only — never full values or secrets.
    remote: list[str] = []
    for name in sorted(candidates):
        if not URL_NAME_RE.search(name):
            continue
        value = effective(name, dotenv)
        if not value:
            continue
        host = (urlparse(value).hostname or "").lower()
        if host and host not in LOCAL_DB_HOSTS:
            remote.append(f"{name} → {host}")
    if remote:
        warn(
            "endpoint vars point at non-local hosts (name + host only)",
            "; ".join(remote) + " — these will fail offline at the venue",
        )
    else:
        ok("all *_URL endpoint vars are local or unset")


def main() -> int:
    try:  # classic conhost may be cp1252; the check marks need utf-8
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError) as exc:  # stdout replaced/closed
        print(f"note: stdout stays in its default encoding ({type(exc).__name__})", file=sys.stderr)

    parser = argparse.ArgumentParser(description="BebshaX offline-demo preflight gate")
    parser.add_argument(
        "--strict-offline",
        action="store_true",
        help=(
            "additionally fail/warn on cloud reliance: *_API_KEY-style vars, remote *_URL "
            "hosts, and a Neon tenant URL baked into apps/frontend/dist"
        ),
    )
    args = parser.parse_args()

    print("BebshaX demo preflight — offline exhibition readiness")
    print(f"repo: {REPO_ROOT}\n")

    dotenv = parse_dotenv(ENV_FILE)

    print("[env]")
    db_url = check_env_file(dotenv)
    check_jwt_secret(dotenv)

    print("\n[database]")
    check_docker_db()
    if db_url:
        check_database(db_url)

    print("\n[datasets — evidence grounding]")
    check_processed_datasets()

    print("\n[ollama — offline fallback pool]")
    check_ollama()

    print("\n[backend]")
    check_backend_health()

    if args.strict_offline:
        print("\n[strict-offline]")
        check_strict_offline(dotenv)
        check_dist_offline()

    print()
    if _failures:
        print(f"RESULT: NOT READY — {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"  \u2717 {f}")
        print("\nDemo-day recipe: copy .env.demo over .env (backup first), then")
        print("  docker compose up -d --wait db")
        print("  cd apps/backend; ..\\..\\.venv\\Scripts\\python -m alembic upgrade head; cd ..\\..")
        print("  node scripts/dev.js   (seeds demo data on first start)")
        return 1
    print("RESULT: READY — all preflight checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
