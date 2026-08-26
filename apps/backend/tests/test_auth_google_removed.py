import pytest
from fastapi.testclient import TestClient
from bebshax.main import app

client = TestClient(app)


def test_google_auth_endpoint_does_not_exist():
    """
    B3 regression guard. Previously: base64-decoded an unverified credential
    (skipped entirely when email+avatar_url were supplied), fell back to
    google.user@example.com on empty body. No real Google verification ever
    existed in this codebase — do not re-add without a real GIS integration,
    signature verification, aud/iss/exp checks, and a fresh security review.
    """
    response = client.post("/api/auth/google", json={})
    assert response.status_code in (404, 405)


def test_google_auth_not_in_openapi_schema():
    schema = client.get("/openapi.json").json()
    assert "/api/auth/google" not in schema.get("paths", {})
