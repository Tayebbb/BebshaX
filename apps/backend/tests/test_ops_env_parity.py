"""Ops invariants that only a file scan can catch (2026-09-06 hardening).

- every `Settings` field is documented in .env.example (name parity);
- the demo/exhibition compose profile keeps its restart/healthcheck/ordering;
- the nginx SPA location keeps its security headers;
- CI keeps the checks the hardening wave added.

No docker/network involved — plain file parsing, so it runs in the unit suite.
"""

from __future__ import annotations

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


def _ci_commands(job_name: str) -> list[list[str]]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return [
        shlex.split(command)
        for step in workflow["jobs"][job_name]["steps"]
        for command in step.get("run", "").splitlines()
        if command.strip()
    ]


@pytest.mark.parametrize("job_name", ["backend", "typecheck", "migration-drift"])
def test_ci_python_job_installs_editable_ml_package_with_backend(job_name: str) -> None:
    assert [
        "pip", "install", "-e", "ml_persona", "-e", "apps/backend[dev]",
    ] in _ci_commands(job_name), f"{job_name} must install both local packages"


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


def test_ci_typecheck_keeps_separate_pyright_install() -> None:
    assert ["pip", "install", "pyright"] in _ci_commands("typecheck")


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
        ("ml_persona/constraints.txt", "./ml_persona/"),
        ("ml_persona/src", "./ml_persona/src"),
    ],
)
def test_backend_image_copies_ml_package_before_install(source: str, destination: str) -> None:
    dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    copy_command = f"COPY {source} {destination}"
    assert copy_command in dockerfile
    assert dockerfile.index(copy_command) < dockerfile.index("RUN pip install")


def test_backend_image_installs_both_local_packages() -> None:
    dockerfile = (REPO_ROOT / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")
    install_commands = [
        shlex.split(line)
        for line in dockerfile.splitlines()
        if line.startswith("RUN pip install")
    ]
    assert install_commands == [
        [
            "RUN", "pip", "install", "--constraint", "./ml_persona/constraints.txt",
            "./ml_persona", ".",
        ],
    ]


def test_local_setup_installs_editable_ml_package_with_backend() -> None:
    with patch.object(
        setup_script.subprocess, "run", return_value=subprocess.CompletedProcess([], 0),
    ) as subprocess_run:
        setup_script.install_backend()

    subprocess_run.assert_called_once_with(
        [
            str(setup_script.VENV_PY), "-m", "pip", "install",
            "-e", str(setup_script.ROOT / "ml_persona"),
            "-e", str(setup_script.ROOT / "apps" / "backend") + "[dev]",
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
