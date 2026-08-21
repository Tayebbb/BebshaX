from bebshax.config import Settings


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
