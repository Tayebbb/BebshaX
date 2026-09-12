"""Offline Python 3.12 verification entry point for the runtime integration batch."""

import os
import sys


def run() -> int:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Runtime verification requires Python 3.12")
    system_root = os.environ.get("SystemRoot", "C:/Windows")
    os.environ.clear()
    os.environ.update({
        "SystemRoot": system_root,
        "BEBSHAX_JWT_SECRET": "runtime-test-only-key-0123456789abcdef",
        "BEBSHAX_ENVIRONMENT": "test",
        "PYTHONNOUSERSITE": "1",
    })
    from unittest.mock import AsyncMock, patch

    import asyncpg
    import dotenv
    import pytest
    from pydantic_settings import DotEnvSettingsSource

    with (
        patch.object(dotenv, "load_dotenv", return_value=False),
        patch.object(DotEnvSettingsSource, "_read_env_files", return_value={}),
        patch.object(asyncpg, "connect", AsyncMock(side_effect=AssertionError("Live PostgreSQL is forbidden"))),
    ):
        return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(run())