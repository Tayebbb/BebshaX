from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class OpsConfigTests(unittest.TestCase):
    def test_compose_private_network_and_runtime_limits(self) -> None:
        config = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        self.assertTrue(config["networks"]["database"]["internal"])
        self.assertEqual(config["services"]["db"]["ports"], ["127.0.0.1:5433:5432"])
        for name in ("app", "web"):
            service = config["services"][name]
            self.assertTrue(service["read_only"])
            self.assertNotIn("env_file", service)
            self.assertEqual(service["cap_drop"], ["ALL"])
            self.assertIn("no-new-privileges:true", service["security_opt"])
            for setting in ("mem_limit", "cpus", "pids_limit", "logging", "restart", "healthcheck"):
                self.assertIn(setting, service)

    def test_readiness_outer_budget_exceeds_client_and_database_budgets(self) -> None:
        def value(relative: str, name: str) -> float:
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
            return float(ast.literal_eval(assignment.value))
        db = value("apps/backend/bebshax/api/health.py", "DB_PROBE_TIMEOUT_S")
        client = value("deploy/healthcheck.py", "TIMEOUT_SECONDS")
        config = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        outer = float(config["services"]["app"]["healthcheck"]["timeout"].removesuffix("s"))
        self.assertGreater(client, db)
        self.assertGreater(outer, client)

    def test_model_mount_is_immutable_and_not_implicitly_created(self) -> None:
        config = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        app = config["services"]["app"]
        mount = next(volume for volume in app["volumes"] if isinstance(volume, dict))
        self.assertTrue(mount["read_only"])
        self.assertFalse(mount["bind"]["create_host_path"])
        self.assertEqual(app["environment"]["BEBSHAX_ML_PERSONA_REQUIRED"], "true")
        self.assertEqual(app["environment"]["BEBSHAX_DEMO_MODE"], "false")
        self.assertEqual(app["environment"]["BEBSHAX_CORS_ORIGIN_REGEX"], "")

    def test_proxy_idle_budget_outlasts_current_maximum_request_deadline(self) -> None:
        tree = ast.parse((ROOT / "apps/backend/bebshax/llm/latency.py").read_text(encoding="utf-8"))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == "REQUEST_DEADLINE_CAP_S" for target in node.targets))
        deadline = float(ast.literal_eval(assignment.value))
        nginx = (ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")
        idle = float(re.search(r"proxy_read_timeout ([0-9]+)s;", nginx)[1])
        self.assertGreater(idle, deadline)
        self.assertNotIn("$request_uri", nginx)
        self.assertNotIn("$http_referer", nginx)

    def test_actions_are_commit_pinned_and_no_job_ignores_failure(self) -> None:
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            config = yaml.safe_load(workflow.read_text(encoding="utf-8"))
            self.assertEqual(config["permissions"]["contents"], "read")
            for job in config["jobs"].values():
                self.assertFalse(job.get("continue-on-error", False))
                for step in job.get("steps", []):
                    self.assertFalse(step.get("continue-on-error", False))
                    if "uses" in step:
                        self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")

    def test_existing_coverage_migration_and_secret_gates_are_preserved(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for gate in ("coverage combine", "--fail-under=68", "alembic upgrade head", "test_pg_integration.py", "gitleaks", "pip_audit", "scripts/ops/typecheck.py"):
            self.assertIn(gate, source)

    def test_backend_shards_cover_every_test_directory_exactly_once(self) -> None:
        config = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        shards = {entry["shard"]: entry["paths"] for entry in config["jobs"]["backend"]["strategy"]["matrix"]["include"]}
        self.assertEqual(config["jobs"]["coverage-gate"]["needs"], "backend")
        self.assertIn("--cov=bebshax", config["jobs"]["backend"]["steps"][-2]["run"])
        # The catch-all shard excludes exactly what the named shards run, so a new
        # test directory is collected by CI without editing the matrix.
        named = {"apps/backend/tests/api", "apps/backend/tests/auth", "apps/backend/tests/test_*.py"}
        excluded = set(re.findall(r"--ignore(?:-glob)?='?([^\s']+)'?", shards["services"]))
        self.assertEqual(excluded, named)
        self.assertEqual(shards["core"].split(), ["apps/backend/tests/test_*.py", "apps/backend/tests/auth"])
        api_ignores = {re.search(r"test_\[([a-z])-([a-z])\]", shards[name])[0] for name in ("api-a", "api-m")}
        self.assertEqual(api_ignores, {"test_[m-z]", "test_[a-l]"})

    def test_web_build_uses_root_workspace_lock_and_reviewed_images(self) -> None:
        source = (ROOT / "deploy/web.Dockerfile").read_text(encoding="utf-8")
        images = json.loads((ROOT / "deploy/images.json").read_text(encoding="utf-8"))["images"]
        self.assertIn("COPY package.json package-lock.json ./", source)
        self.assertNotIn("apps/frontend/package-lock.json", source)
        self.assertIn("npm ci --workspaces --include-workspace-root", source)
        self.assertIn("USER 101:101", source)
        for name in ("node", "nginx"):
            self.assertIn(f"{name}:{images[name]['tag']}@{images[name]['digest']}", source)
        for instruction in re.findall(r"^FROM (.+)$", source, re.MULTILINE):
            self.assertRegex(instruction, r"@sha256:[0-9a-f]{64}")


if __name__ == "__main__":
    unittest.main()