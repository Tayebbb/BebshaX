"""Run scoped security tests without loading workstation credentials."""

import os
from pathlib import Path
import secrets
import sys
from unittest.mock import patch


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Security checks require the project Python 3.12 environment.")
    root = Path(__file__).resolve().parents[4]
    os.chdir(root)
    os.environ.update({
        "BEBSHAX_JWT_SECRET": secrets.token_urlsafe(48),
        "BEBSHAX_JWT_SECRET_PREVIOUS": "",
        "BEBSHAX_DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "BEBSHAX_ENVIRONMENT": "development",
        "BEBSHAX_RATE_LIMIT_STORAGE_URI": "",
        "BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR": "false",
        "BEBSHAX_NEON_AUTH_URL": "",
        "BEBSHAX_RESEND_API_KEY": "",
        "BEBSHAX_SMTP_USERNAME": "",
        "BEBSHAX_SMTP_PASSWORD": "",
        "BEBSHAX_STRIPE_SECRET_KEY": "",
        "BEBSHAX_STRIPE_PUBLISHABLE_KEY": "",
        "BEBSHAX_STRIPE_WEBHOOK_SECRET": "",
        "BEBSHAX_PAYMENTS_ENABLED": "false",
        "BEBSHAX_DEMO_MODE": "false",
        "BEBSHAX_EMBEDDING_BACKEND": "local",
        "COVERAGE_CORE": "sysmon",
        "COVERAGE_FILE": str(Path(__file__).parent / "__pycache__" / ".coverage-security"),
    })
    blocked = AssertionError("External network transport is disabled in security unit checks")
    with (
        patch("pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}),
        patch("dotenv.load_dotenv", return_value=False),
        patch("httpx.HTTPTransport.handle_request", side_effect=blocked),
        patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=blocked),
        patch("smtplib.SMTP.connect", side_effect=blocked),
    ):
        import pytest

        return pytest.main([
            "-c", str(root / "apps/backend/pyproject.toml"),
            "--basetemp", str(Path(__file__).parent / "__pycache__" / secrets.token_hex(12)),
            *sys.argv[1:],
        ])


if __name__ == "__main__":
    raise SystemExit(main())