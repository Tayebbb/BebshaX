import pytest

from bebshax.config import Settings


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in Settings.model_fields:
        monkeypatch.delenv(f"BEBSHAX_{field.upper()}", raising=False)
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "test-config-only-secret-not-for-production-0123456789")


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.app_name == "BebshaX"
    assert s.demo_mode is False
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BEBSHAX_DEMO_MODE", "true")
    monkeypatch.setenv("BEBSHAX_ENVIRONMENT", "test")
    s = Settings(_env_file=None)
    assert s.demo_mode is True
    assert s.environment == "test"


def test_blank_remote_processing_policy_reads_as_unset(monkeypatch) -> None:
    """Hosting dashboards and env templates ship empty values; a blank policy
    must derive the default at startup, never crash boot or deny everything."""
    monkeypatch.setenv("BEBSHAX_REMOTE_PROCESSING_POLICY", "   ")
    s = Settings(_env_file=None)
    assert "remote_processing_policy" not in s.model_fields_set
    assert s.remote_processing_policy == Settings(_env_file=None).remote_processing_policy


def test_explicit_remote_processing_policy_json_is_parsed(monkeypatch) -> None:
    monkeypatch.setenv(
        "BEBSHAX_REMOTE_PROCESSING_POLICY",
        '{"policy_id": "pinned", "private_providers": ["freellmpool"], "synthetic_providers": ["freellmpool"]}',
    )
    s = Settings(_env_file=None)
    assert "remote_processing_policy" in s.model_fields_set
    assert s.remote_processing_policy.policy_id == "pinned"
    assert set(s.remote_processing_policy.private_providers) == {"freellmpool"}
