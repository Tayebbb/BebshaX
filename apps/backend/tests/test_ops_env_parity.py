"""Ops invariants that only a file scan can catch (2026-09-06 hardening).

- every `Settings` field is documented in .env.example (name parity);
- the demo/exhibition compose profile keeps its restart/healthcheck/ordering;
- the nginx SPA location keeps its security headers;
- CI keeps the checks the hardening wave added.

No docker/network involved — plain file parsing, so it runs in the unit suite.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from packaging.requirements import Requirement

from bebshax.config import Settings
from scripts import setup as setup_script

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE = REPO_ROOT / "docker-compose.yml"
NGINX_CONF = REPO_ROOT / "deploy" / "nginx.conf"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
ML_RUNTIME_CONSTRAINTS = REPO_ROOT / "ml_persona" / "constraints.txt"

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


def test_app_container_requires_explicit_migration_before_serving() -> None:
    service = _compose()["services"]["app"]
    assert "command" not in service
    dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    command = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
    entrypoint = json.loads(next(
        line[11:] for line in dockerfile.splitlines() if line.startswith("ENTRYPOINT ")
    ))
    assert command[:4] == ["python", "-m", "uvicorn", "bebshax.main:app"]
    assert entrypoint == ["python", "/app/deploy/runtime_config.py"]
    assert "alembic" not in command
    assert service["init"] is True


def test_app_container_mounts_durable_data_and_immutable_artifacts() -> None:
    assert re.search(r"^data/\s*$", DOCKERIGNORE.read_text(encoding="utf-8"), re.MULTILINE)
    compose = _compose()
    service = compose["services"]["app"]
    volumes = service["volumes"]
    assert "bebshax_appdata:/app/data" in volumes
    assert "bebshax_appdata" in compose["volumes"]
    artifact_mount = next(volume for volume in volumes if isinstance(volume, dict))
    assert artifact_mount["type"] == "bind"
    assert artifact_mount["target"] == "/app/artifacts"
    assert artifact_mount["read_only"] is True
    assert artifact_mount["bind"]["create_host_path"] is False
    assert service["read_only"] is True
    assert service["user"] == "10001:10001"


def test_compose_base_images_are_pinned_to_versioned_digests() -> None:
    web_dockerfile = (REPO_ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
    app_dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    froms = re.findall(r"^FROM\s+(\S+)", web_dockerfile + "\n" + app_dockerfile, re.MULTILINE)
    assert froms, "no FROM lines found"
    for image in froms:
        assert not image.endswith(":latest") and ":" in image, f"floating base image: {image}"
        tag = image.split(":", 1)[1].split("@", 1)[0]
        assert re.match(r"^\d+\.\d+", tag), f"tag must carry major.minor: {image}"
        assert re.search(r"@sha256:[0-9a-f]{64}$", image), f"missing immutable digest: {image}"


def test_nginx_spa_inherits_security_headers_and_built_csp() -> None:
    conf = NGINX_CONF.read_text(encoding="utf-8")
    server_headers = re.split(r"^\s*location\s", conf.split("server {", 1)[1], maxsplit=1, flags=re.MULTILINE)[0]
    assert "add_header_inherit merge;" in server_headers
    for header in (
        'X-Frame-Options "DENY"',
        'X-Content-Type-Options "nosniff"',
        'Referrer-Policy "strict-origin-when-cross-origin"',
        "Permissions-Policy",
        "Content-Security-Policy",
    ):
        assert header in server_headers, f"nginx server lost inherited header: {header}"
    assert 'Content-Security-Policy "__BEBSHAX_CSP__" always;' in server_headers
    policy_source = (REPO_ROOT / "scripts" / "ops" / "web-config.mjs").read_text(encoding="utf-8")
    assert "script-src 'self'" in policy_source and "'unsafe-eval'" not in policy_source
    assert "frame-ancestors 'none'" in policy_source
    dockerfile = (REPO_ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
    assert "node scripts/ops/web-config.mjs nginx deploy/nginx.conf /build/nginx.conf" in dockerfile
    assert "COPY --from=build /build/nginx.conf /etc/nginx/nginx.conf" in dockerfile
    # SSE proxying must stay unbuffered regardless of header work.
    assert "proxy_buffering off;" in conf


def test_ci_keeps_hardening_steps() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    frontend_runs = [step.get("run", "") for step in jobs["frontend"]["steps"]]
    assert "npm run theme:check" in frontend_runs
    node_version = next(
        step["with"]["node-version"] for step in jobs["frontend"]["steps"]
        if "node-version" in step.get("with", {})
    )
    web_dockerfile = (REPO_ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
    image_node_version = re.search(r"^FROM node:(\d+\.\d+\.\d+)-", web_dockerfile, re.MULTILINE)
    assert image_node_version is not None
    assert str(node_version) == image_node_version.group(1), "CI and image Node pins must match"
    backend_runs = " ".join(step.get("run", "") for step in jobs["backend"]["steps"])
    assert "pip_audit" in backend_runs
    drift_runs = " ".join(step.get("run", "") for step in jobs["migration-drift"]["steps"])
    assert 'test "$head_count" = "1"' in drift_runs, "multi-head alembic chains must fail CI"
    compose_runs = " ".join(step.get("run", "") for step in jobs["compose-config"]["steps"])
    assert "python scripts/ops/compose_check.py" in compose_runs


def _ci_commands(job_name: str) -> list[list[str]]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        shlex.split(command)
        for step in workflow["jobs"][job_name]["steps"]
        for command in step.get("run", "").splitlines()
        if command.strip()
    ]


@pytest.mark.parametrize(
    ("job_name", "install_command"),
    [
        ("backend", ["python", "scripts/ops/dependencies.py", "install", "--wheelhouse", ".tmp/wheelhouse"]),
        ("typecheck", [".venv/bin/python", "scripts/ops/dependencies.py", "install"]),
        ("migration-drift", ["python", "scripts/ops/dependencies.py", "install"]),
    ],
)
def test_ci_python_jobs_use_reviewed_locked_installer(job_name: str, install_command: list[str]) -> None:
    assert install_command in _ci_commands(job_name)


def test_ci_backend_runs_ml_tests_in_isolation() -> None:
    assert ["python", "-m", "pytest", "ml_persona/tests", "-q"] in _ci_commands("backend")


def test_ci_lints_ml_source_and_tests_with_shared_bug_tier_config() -> None:
    lint_command = next(
        command for command in _ci_commands("backend")
        if command[:4] == ["python", "-m", "ruff", "check"]
    )
    assert {"ml_persona/src", "ml_persona/tests"} <= set(lint_command)
    assert "--config" in lint_command
    assert lint_command[lint_command.index("--config") + 1] == "apps/backend/pyproject.toml"


def test_ci_backend_preserves_coverage_floor() -> None:
    assert [
        "python", "-m", "pytest", "apps/backend/tests", "-q",
        "--cov=bebshax", "--cov-fail-under=68",
    ] in _ci_commands("backend")


def test_ci_typecheck_uses_locked_pyright_in_isolated_environment() -> None:
    commands = _ci_commands("typecheck")
    assert ["python", "-m", "venv", ".venv"] in commands
    assert [".venv/bin/python", "scripts/ops/typecheck.py", "apps/backend/bebshax"] in commands
    assert ["pip", "install", "pyright"] not in commands


def test_ml_runtime_constraints_pin_trained_artifact_versions_exactly() -> None:
    constraints = [
        line.strip()
        for line in ML_RUNTIME_CONSTRAINTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert sorted(constraints) == [
        "numpy==2.5.2",
        "scikit-learn==1.9.0",
        "scipy==1.18.1",
    ]


@pytest.mark.parametrize("dependency", ["numpy", "scipy", "scikit-learn"])
def test_ml_runtime_constraint_is_exact_and_within_declared_bounds(dependency: str) -> None:
    manifest = tomllib.loads(
        (REPO_ROOT / "ml_persona" / "pyproject.toml").read_text(encoding="utf-8"),
    )
    requirements = {
        requirement.name: requirement
        for requirement in map(Requirement, manifest["project"]["dependencies"])
    }
    constraints = [
        Requirement(line)
        for line in ML_RUNTIME_CONSTRAINTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    constraint = next(requirement for requirement in constraints if requirement.name == dependency)
    specifiers = list(constraint.specifier)
    assert len(specifiers) == 1
    specifier = specifiers[0]
    assert specifier.operator == "=="
    assert "*" not in specifier.version
    assert specifier.version in requirements[dependency].specifier


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("ml_persona/pyproject.toml", "./ml_persona/"),
        ("ml_persona/constraints.txt", "./constraints.txt"),
        ("ml_persona/src", "./ml_persona/src"),
    ],
)
def test_backend_image_copies_ml_package_before_wheel_build(source: str, destination: str) -> None:
    dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    copy_command = f"COPY {source} {destination}"
    assert copy_command in dockerfile
    assert dockerfile.index(copy_command) < dockerfile.index("RUN python -m pip --isolated wheel")


def test_backend_image_builds_both_packages_and_installs_offline_wheels() -> None:
    dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    build_command = next(
        shlex.split(line) for line in dockerfile.splitlines()
        if line.startswith("RUN python -m pip --isolated wheel")
    )
    assert build_command[-2:] == ["./ml_persona", "./apps/backend"]
    assert {"--no-deps", "--no-build-isolation", "--no-index"} <= set(build_command)
    runtime_stage = dockerfile.rsplit("FROM ", 1)[1]
    assert "COPY deploy/python/runtime.lock ./requirements.lock" in runtime_stage
    assert "--require-hashes --only-binary=:all:" in runtime_stage
    assert "COPY --from=build /local-wheels /local-wheels" in runtime_stage
    assert "RUN python -m pip --isolated install --no-deps --no-index /local-wheels/*.whl" in runtime_stage


def test_local_setup_uses_reviewed_locked_backend_installer() -> None:
    with patch.object(
        setup_script.subprocess, "run", return_value=subprocess.CompletedProcess([], 0),
    ) as subprocess_run:
        setup_script.install_backend()

    subprocess_run.assert_called_once_with(
        [
            str(setup_script.VENV_PY),
            str(setup_script.ROOT / "scripts" / "ops" / "dependencies.py"), "install",
        ],
        cwd=setup_script.ROOT,
        check=True,
    )


def test_local_setup_propagates_backend_install_failure() -> None:
    failure = subprocess.CalledProcessError(1, ["pip", "install"])
    with patch.object(setup_script.subprocess, "run", side_effect=failure):
        with pytest.raises(subprocess.CalledProcessError) as raised:
            setup_script.install_backend()

    assert raised.value is failure
