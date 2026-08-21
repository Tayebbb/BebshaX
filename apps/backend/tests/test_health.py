from fastapi.testclient import TestClient

from bebshax import __version__
from bebshax.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "BebshaX"
    assert body["version"] == __version__
