"""Offline SEC01 runner; no dotenv reads or parent-process environment changes."""

from pathlib import Path
import os
import subprocess
import sys
from unittest.mock import patch


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("SEC01 checks require the project Python 3.12 venv")
    root = Path(__file__).resolve().parents[4]
    if "--isolated-child" not in sys.argv:
        child_environment = {
            key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT")
            if key in os.environ
        }
        child_environment.update({
            "BEBSHAX_JWT_SECRET": "test-only-jwt-secret-not-for-production-0123456789",
            "BEBSHAX_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "BEBSHAX_ENV": "test",
            "BEBSHAX_EMBEDDING_BACKEND": "local",
            "BEBSHAX_DEMO_MODE": "false",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "TEMP": str(root / ".tmp"), "TMP": str(root / ".tmp"),
        })
        return subprocess.call(
            [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--isolated-child", *sys.argv[1:]],
            cwd=root, env=child_environment,
        )
    arguments = [argument for argument in sys.argv[1:] if argument != "--isolated-child"]
    with patch("pydantic_settings.sources.providers.dotenv.DotEnvSettingsSource._read_env_files", return_value={}):
        import bebshax.auth.models
        import bebshax.interview.orm
        import bebshax.personas.orm
        import pytest

        return pytest.main([
            *arguments, "--no-cov", "--tb=short", "--show-capture=no",
            "-o", f"cache_dir={root / '.tmp' / 'sec01-cache'}",
        ])


if __name__ == "__main__":
    raise SystemExit(main())