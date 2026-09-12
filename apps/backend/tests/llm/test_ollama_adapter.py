"""Retired real-adapter coverage is replaced by remote transport contract tests."""

from bebshax.llm.adapters import ollama_adapter


def test_retired_module_contains_no_executable_local_adapter() -> None:
    assert not hasattr(ollama_adapter, "OllamaAdapter")
    assert not hasattr(ollama_adapter, "httpx")
    assert not hasattr(ollama_adapter, "DEFAULT_BASE_URL")
