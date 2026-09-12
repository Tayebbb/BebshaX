from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch


def main() -> int:
    label, *arguments = sys.argv[1:]
    if not re.fullmatch(r"[a-z0-9-]+", label) or not arguments:
        raise ValueError("Provide a lowercase receipt label and focused pytest arguments.")
    receipt_directory = Path(__file__).parent
    started = time.monotonic()
    output_path = receipt_directory / f".domain-{label}.stdout"
    with output_path.open("w", encoding="utf-8") as output, ExitStack() as stack:
        stack.enter_context(redirect_stdout(output))
        stack.enter_context(redirect_stderr(output))
        environment = {
            name: os.environ[name] for name in (
                "PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA",
                "USERPROFILE", "COMSPEC", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
            ) if name in os.environ
        }
        environment.update({
            "BEBSHAX_JWT_SECRET": "test-only-domain-jobs-signing-material-0123456789",
            "BEBSHAX_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "COVERAGE_FILE": str(receipt_directory / f".domain-{label}.coverage"),
        })
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}))
        import pytest

        exit_code = int(pytest.main([
            "--disable-plugin-autoload", "-p", "pytest_asyncio.plugin", "-p", "pytest_cov.plugin",
            "-c", "apps/backend/pyproject.toml", "-p", "no:cacheprovider", "--tb=short", *arguments,
        ]))
    receipt = {
        "label": label, "exit_code": exit_code, "arguments": arguments,
        "elapsed_seconds": round(time.monotonic() - started, 3), "python": sys.executable,
    }
    (receipt_directory / f".domain-{label}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    sys.stdout.write(json.dumps(receipt) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())