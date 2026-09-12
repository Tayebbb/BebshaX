"""Production composition cannot restore retired local discovery."""

from bebshax.llm.adapters.factory import build_default_adapters


async def test_legacy_local_setting_does_not_add_discovery_or_an_adapter(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:11434")
    adapters = build_default_adapters()
    try:
        assert set(adapters) == {"freellmpool", "openrouter"}
    finally:
        for adapter in adapters.values():
            await adapter.aclose()
