import importlib
import pytest
from bebshax.config import Settings


def test_app_refuses_to_start_without_resend_key_in_production(monkeypatch):
    """Fail-fast: in production, missing BEBSHAX_RESEND_API_KEY must raise ValueError during Settings construction."""
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "a" * 48)
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "production")
    monkeypatch.delenv("BEBSHAX_RESEND_API_KEY", raising=False)

    with pytest.raises(ValueError, match="BEBSHAX_RESEND_API_KEY is required in production/staging environments"):
        Settings()


def test_app_starts_without_resend_key_in_local_dev(monkeypatch):
    """In local development, missing BEBSHAX_RESEND_API_KEY is allowed and does not block startup."""
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "a" * 48)
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "development")
    monkeypatch.delenv("BEBSHAX_RESEND_API_KEY", raising=False)

    s = Settings()
    assert s.resend_api_key is None
