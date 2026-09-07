"""Ops invariants that only a file scan can catch (2026-09-06 hardening).

- every `Settings` field is documented in .env.example (name parity);
- the demo/exhibition compose profile keeps its restart/healthcheck/ordering;
- the nginx SPA location keeps its security headers;
- CI keeps the checks the hardening wave added.

No docker/network involved — plain file parsing, so it runs in the unit suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from bebshax.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE = REPO_ROOT / "docker-compose.yml"
NGINX_CONF = REPO_ROOT / "deploy" / "nginx.conf"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

_ENV_NAME_RE = re.compile(r"^\s*#?\s*(BEBSHAX_[A-Z0-9_]+)=", re.MULTILINE)


def _documented_env_names() -> set[str]:
    return set(_ENV_NAME_RE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _expected_env_names() -> set[str]:
    return {f"BEBSHAX_{name.upper()}" for name in Settings.model_fields}


def test_every_settings_field_is_documented_in_env_example() -> None:
    missing = _expected_env_names() - _documented_env_names()
    assert not missing, (
        f".env.example is missing {sorted(missing)} — add each with a safe/empty "
        "value and a one-line comment (RULES.md R4 documents names, never values)"
    )


def test_env_example_carries_no_real_secret_values() -> None:
    """Placeholders only: a real key shape in the template is a leak (R4)."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for pattern in (r"sk-or-v1-[0-9a-f]{20,}", r"npg_[A-Za-z0-9]{12,}", r"re_[A-Za-z0-9]{20,}"):
        assert not re.search(pattern, text), f"secret-shaped value in .env.example: {pattern}"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_full_profile_services_restart_and_have_healthchecks() -> None:
    services = _compose()["services"]
    for name in ("app", "web"):
        svc = services[name]
        assert "full" in svc.get("profiles", []), f"{name} must stay behind the full profile"
        assert svc.get("restart") == "unless-stopped", f"{name} lost restart: unless-stopped"
        assert svc.get("healthcheck", {}).get("test"), f"{name} lost its healthcheck"


def test_full_profile_startup_order_gates_on_health() -> None:
    services = _compose()["services"]
    assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["web"]["depends_on"]["app"]["condition"] == "service_healthy"


def test_app_container_migrates_before_serving() -> None:
    command = _compose()["services"]["app"]["command"]
    assert "alembic upgrade head" in command
    assert command.index("alembic upgrade head") < command.index("uvicorn")
    assert "exec python -m uvicorn" in command, "uvicorn must exec so it is PID 1 (SIGTERM)"


def test_app_container_mounts_grounding_data_read_only() -> None:
    """.dockerignore drops data/ from the image; the mounts put it back."""
    assert re.search(r"^data/\s*$", DOCKERIGNORE.read_text(encoding="utf-8"), re.MULTILINE)
    volumes = _compose()["services"]["app"]["volumes"]
    assert "./data/processed:/app/data/processed:ro" in volumes
    assert "./data/metadata:/app/data/metadata:ro" in volumes


def test_compose_base_images_are_pinned_to_minor_tags() -> None:
    web_dockerfile = (REPO_ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
    app_dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    froms = re.findall(r"^FROM\s+(\S+)", web_dockerfile + "\n" + app_dockerfile, re.MULTILINE)
    assert froms, "no FROM lines found"
    for image in froms:
        assert not image.endswith(":latest") and ":" in image, f"floating base image: {image}"
        tag = image.split(":", 1)[1].split("@", 1)[0]
        assert re.match(r"^\d+\.\d+", tag), f"tag must carry major.minor: {image}"


def test_nginx_spa_location_sets_security_headers() -> None:
    conf = NGINX_CONF.read_text(encoding="utf-8")
    spa_block = conf.split("location / {", 1)[1]
    for header in (
        'X-Frame-Options "DENY"',
        'X-Content-Type-Options "nosniff"',
        'Referrer-Policy "strict-origin-when-cross-origin"',
        "Permissions-Policy",
        "Content-Security-Policy",
    ):
        assert header in spa_block, f"nginx SPA location lost header: {header}"
    csp = re.search(r'Content-Security-Policy "([^"]+)"', spa_block).group(1)
    assert "script-src 'self'" in csp and "'unsafe-eval'" not in csp
    assert "frame-ancestors 'none'" in csp
    # SSE proxying must stay unbuffered regardless of header work.
    assert "proxy_buffering off;" in conf


def test_ci_keeps_hardening_steps() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    frontend_runs = [step.get("run", "") for step in jobs["frontend"]["steps"]]
    assert "npm run theme:check" in frontend_runs
    node_version = next(
        step["with"]["node-version"] for step in jobs["frontend"]["steps"] if "with" in step
    )
    assert str(node_version) == "24", "CI Node major must match deploy/web.Dockerfile"
    backend_runs = " ".join(step.get("run", "") for step in jobs["backend"]["steps"])
    assert "pip_audit" in backend_runs
    drift_runs = " ".join(step.get("run", "") for step in jobs["migration-drift"]["steps"])
    assert 'test "$head_count" = "1"' in drift_runs, "multi-head alembic chains must fail CI"
    compose_runs = " ".join(step.get("run", "") for step in jobs["compose-config"]["steps"])
    assert "docker compose --profile full config --quiet" in compose_runs
