"""Run DB checks with synthetic settings, no dotenv reads, and repository-local temps."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch


def main() -> int:
    sys.dont_write_bytecode = True
    test_directory = Path(__file__).resolve().parent
    repository = test_directory.parents[3]
    arguments = sys.argv[1:] or [str(test_directory)]
    system_environment = {
        name: os.environ[name]
        for name in ("SYSTEMROOT", "WINDIR", "PATH", "COMSPEC", "PATHEXT")
        if name in os.environ
    }
    with TemporaryDirectory(prefix=".db-integrator-", dir=test_directory) as temporary:
        os.environ.clear()
        os.environ.update(system_environment)
        os.environ.update({
            "HOME": temporary,
            "USERPROFILE": temporary,
            "APPDATA": temporary,
            "LOCALAPPDATA": temporary,
            "TEMP": temporary,
            "TMP": temporary,
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "BEBSHAX_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "BEBSHAX_ENVIRONMENT": "development",
            "BEBSHAX_DEMO_MODE": "false",
            "BEBSHAX_EMBEDDING_BACKEND": "local",
            "BEBSHAX_JWT_SECRET": "synthetic-db-test-only-0123456789abcdef0123456789",
        })
        os.chdir(repository)
        sys.path.insert(0, str(repository / "apps" / "backend"))
        sys.path.insert(0, str(repository))
        with patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}):
            import pytest

            return int(pytest.main([
                "--confcutdir", str(test_directory),
                "--basetemp", str(Path(temporary) / "pytest"),
                "-o", f"cache_dir={Path(temporary) / 'cache'}",
                "--no-cov",
                *arguments,
            ]))


if __name__ == "__main__":
    raise SystemExit(main())