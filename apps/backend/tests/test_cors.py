"""M6 regression: CORS must echo only configured origins — never `*` with credentials."""

import pytest
from fastapi.testclient import TestClient

from bebshax.config import Settings, get_settings
from bebshax.main import create_app


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


@pytest.fixture
def _default_origins(monkeypatch):
    """Isolate from a developer's .env / cached settings so defaults apply."""
    monkeypatch.delenv("BEBSHAX_CORS_ORIGINS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_allowed_origin_is_echoed_not_wildcard(_default_origins) -> None:
    app = create_app()
    client = TestClient(app)  # no lifespan needed for middleware
    resp = _preflight(client, "http://localhost:5173")
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_unknown_origin_is_rejected(_default_origins) -> None:
    app = create_app()
    client = TestClient(app)
    resp = _preflight(client, "https://evil.example.com")
    assert "access-control-allow-origin" not in resp.headers


def test_cors_origins_parsing_tolerates_whitespace(monkeypatch) -> None:
    monkeypatch.setenv("BEBSHAX_CORS_ORIGINS", " https://app.example.com , http://localhost:5173 ")
    get_settings.cache_clear()
    try:
        assert Settings().cors_origins_list == [
            "https://app.example.com",
            "http://localhost:5173",
        ]
    finally:
        get_settings.cache_clear()
