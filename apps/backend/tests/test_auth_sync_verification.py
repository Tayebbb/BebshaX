import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base
from bebshax.main import app

# Ensure app has a working sessionmaker for the test client
_engine = create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="module", autouse=True)
def _setup_app_db():
    import asyncio
    async def init():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init())
    sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_sessionmaker = sm
    app.state.sessionmaker = sm


client = TestClient(app)


def test_sync_rejects_request_with_no_token():
    """B3 regression guard: /sync must require neon_token, not accept bare email."""
    response = client.post("/api/auth/sync", json={"email": "victim@example.com"})
    assert response.status_code == 422  # missing required field


def test_sync_rejects_invalid_neon_token():
    """A token that Neon itself rejects must not mint an app JWT."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        from fastapi import HTTPException
        mock_verify.side_effect = HTTPException(status_code=401, detail="invalid")
        response = client.post(
            "/api/auth/sync", json={"neon_token": "forged-or-garbage-token"}
        )
        assert response.status_code == 401


def test_sync_uses_verified_email_not_claimed_email():
    """Even if a client somehow smuggled a claimed email in, only the verified
    value from Neon's response should ever be used to look up/create the user."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "user": {
                "email": "real-verified@example.com",
                "full_name": "Real User",
                "emailVerified": True,
            }
        }
        response = client.post(
            "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
        )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "real-verified@example.com"


def test_sync_marks_mirror_user_verified():
    """H9: a Neon-verified session flips is_verified on the mirror row so
    backend email/password signins pass the verification gate afterwards."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "user": {
                "email": "h9-flip@example.com",
                "name": "Flip User",
                "emailVerified": True,
            }
        }
        response = client.post(
            "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["is_verified"] is True
        assert body["access_token"]



def test_sync_no_longer_accepts_client_supplied_email_field():
    """The old UserSyncRequest.email field must be gone — confirms the schema
    itself no longer trusts client-claimed identity."""
    import inspect
    from bebshax.api.auth import UserSyncRequest
    fields = UserSyncRequest.model_fields
    assert "email" not in fields or fields["email"].default is not None, (
        "UserSyncRequest still accepts a trusted client-supplied email field"
    )


def test_sync_populates_display_name_and_avatar_from_neon_response():
    """Regression guard: full_name/avatar_url must come from Neon's real
    (nested) response shape, not silently end up None forever."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "user": {
                "id": "usr_test",
                "email": "real-verified@example.com",
                "name": "Real Person",
                "emailVerified": True,
                "image": "https://example.com/avatar.jpg",
            },
            "session": {"token": "valid-token"},
        }
        response = client.post(
            "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
        )
        assert response.status_code == 200
        body = response.json()["user"]
        assert body["full_name"] == "Real Person"
        assert body["avatar_url"] == "https://example.com/avatar.jpg"


def test_sync_rejects_unverified_email():
    """Email must be verified upstream by identity provider."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "user": {"email": "unverified@example.com", "emailVerified": False},
            "session": {"token": "valid-token"},
        }
        response = client.post(
            "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
        )
        assert response.status_code == 401


def test_sync_rejects_missing_emailverified_field():
    """Fail-closed guard: a response with the emailVerified key stripped
    entirely must be rejected, not silently treated as verified."""
    with patch("bebshax.api.auth.verify_neon_token", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "user": {"email": "no-field@example.com"},  # emailVerified key absent
            "session": {"token": "valid-token"},
        }
        response = client.post(
            "/api/auth/sync", json={"neon_token": "valid-token", "auth_provider": "neon"}
        )
        assert response.status_code == 401


