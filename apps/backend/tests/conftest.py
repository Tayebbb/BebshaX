"""Suite-wide fixtures. tests/ is not a package — helpers are shared from here."""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_local_tier(monkeypatch):
    """Point OllamaAdapter at an unroutable port so no unit test ever touches a
    real daemon (connection refused is instant → adapter contributes no routes).
    Adapter-level tests inject their own mock clients and are unaffected."""
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:9")
