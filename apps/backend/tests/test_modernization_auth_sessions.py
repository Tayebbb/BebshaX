"""Persisted sessions, rotation, revocation, and ambient-cookie protections."""

import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.api import auth as auth_api
from bebshax.auth import security
from bebshax.auth.models import Users
from bebshax.config import Settings
from bebshax.db.models import Base


@pytest.fixture
async def session_client(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, jwt_secret=secrets.token_urlsafe(48), jwt_expire_days=365,
        environment="development", require_email_verification=True,
        frontend_base_url="https://app.example.test",
        cors_origins="https://app.example.test", resend_api_key=None,
        smtp_username=None, smtp_password=None,
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api.limiter, "enabled", False)
    monkeypatch.setattr(auth_api, "send_verification_email", AsyncMock(return_value=True))
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        session.add(Users(
            id="usr_session", email="session@example.test", full_name="Session Owner",
            hashed_password=security.hash_password("Session123!"),
            is_verified=True, is_active=True, auth_provider="email",
        ))
        await session.commit()
    app = FastAPI()
    app.include_router(auth_api.auth_router)
    app.state.db_sessionmaker = sessionmaker

    @app.post("/private-write")
    async def private_write(user=Depends(auth_api.get_current_user)):
        return {"user_id": user.id}

    @app.post("/optional-write")
    async def optional_write(user=Depends(auth_api.get_optional_current_user)):
        return {"user_id": user.id if user else None}

    async with AsyncClient(transport=ASGITransport(app), base_url="https://api.example.test") as client:
        yield client, sessionmaker
    await engine.dispose()


async def _signin(client, *, cookie=False):
    response = await client.post(
        "/api/auth/signin", json={"email": "session@example.test", "password": "Session123!"},
        headers={"X-Auth-Transport": "cookie", "Origin": "https://app.example.test"} if cookie else {},
    )
    assert response.status_code == 200
    return response


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def test_signin_persists_jti_and_hashes_refresh_with_bounded_deadlines(session_client):
    client, sessionmaker = session_client
    data = (await _signin(client)).json()
    claims = security.decode_access_token(data["access_token"])
    assert claims["exp"] - claims["iat"] <= 15 * 60
    assert data["expires_in"] <= 15 * 60
    from bebshax.auth.models import AuthSessions
    async with sessionmaker() as session:
        stored = await session.get(AuthSessions, claims["jti"])
        assert stored is not None
        assert stored.refresh_token_hash != data["refresh_token"]
        assert stored.session_version == 0
        assert stored.absolute_expires_at - stored.created_at <= timedelta(days=30)
        assert stored.refresh_expires_at - stored.created_at <= timedelta(days=7)
    assert (await client.get("/api/auth/me", headers=_bearer(data["access_token"]))).status_code == 200


async def test_refresh_rotates_and_replay_revokes_the_entire_family(session_client):
    client, _sessionmaker = session_client
    initial = (await _signin(client)).json()
    response = await client.post("/api/auth/refresh", json={"refresh_token": initial["refresh_token"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != initial["refresh_token"]
    assert rotated["session_id"] == initial["session_id"]
    assert rotated["session_expires_at"] == initial["session_expires_at"]
    replay = await client.post("/api/auth/refresh", json={"refresh_token": initial["refresh_token"]})
    assert replay.status_code == 401
    assert (await client.get("/api/auth/me", headers=_bearer(rotated["access_token"]))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": rotated["refresh_token"]})).status_code == 401


async def test_logout_revokes_own_family_and_old_legacy_credentials_only(session_client):
    client, _sessionmaker = session_client
    legacy = security.create_access_token("usr_session")
    first = (await _signin(client)).json()
    second = (await _signin(client)).json()
    assert (await client.get("/api/auth/me", headers=_bearer(legacy))).status_code == 200
    response = await client.post("/api/auth/logout", headers=_bearer(first["access_token"]))
    assert response.status_code == 200
    for invalid in (first["access_token"], legacy):
        assert (await client.get("/api/auth/me", headers=_bearer(invalid))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})).status_code == 401
    assert (await client.get("/api/auth/me", headers=_bearer(second["access_token"]))).status_code == 200


async def test_logout_all_revokes_both_new_and_legacy_credentials(session_client):
    client, _sessionmaker = session_client
    legacy = security.create_access_token("usr_session")
    first = (await _signin(client)).json()
    second = (await _signin(client)).json()
    response = await client.post("/api/auth/logout-all", headers=_bearer(first["access_token"]))
    assert response.status_code == 200
    for invalid in (first["access_token"], second["access_token"], legacy):
        assert (await client.get("/api/auth/me", headers=_bearer(invalid))).status_code == 401


async def test_cookie_transport_is_http_only_secure_and_requires_origin_and_csrf(session_client):
    client, _sessionmaker = session_client
    signin = await _signin(client, cookie=True)
    assert signin.json()["access_token"] == ""
    assert signin.json().get("refresh_token") is None
    cookies = signin.headers.get_list("set-cookie")
    for name in ("__Host-bebshax_access", "__Secure-bebshax_refresh"):
        cookie = next(value for value in cookies if value.startswith(name + "="))
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie
        assert "Domain=" not in cookie
    csrf = signin.json()["csrf_token"]
    assert (await client.get("/api/auth/me")).status_code == 200
    for path in ("/private-write", "/optional-write", "/api/auth/logout", "/api/auth/refresh"):
        assert (await client.post(path)).status_code == 403
        assert (await client.post(path, headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf})).status_code == 403
    headers = {"Origin": "https://app.example.test", "X-CSRF-Token": csrf}
    assert (await client.post("/private-write", headers=headers)).status_code == 200
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_cookie_login_rejects_untrusted_or_missing_origin(session_client):
    client, _sessionmaker = session_client
    for origin in (None, "null", "https://attacker.example"):
        headers = {"X-Auth-Transport": "cookie"}
        if origin is not None:
            headers["Origin"] = origin
        response = await client.post("/api/auth/signin", headers=headers, json={
            "email": "session@example.test", "password": "Session123!",
        })
        assert response.status_code == 403
        assert not response.headers.get_list("set-cookie")


async def test_browser_bootstrap_can_refresh_expired_access_without_exposing_bearers(session_client):
    client, sessionmaker = session_client
    initial = (await _signin(client, cookie=True)).json()
    from bebshax.auth.models import AuthSessions
    async with sessionmaker() as session:
        row = (await session.execute(select(AuthSessions))).scalar_one()
        row.access_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    bootstrap = await client.get("/api/auth/session", headers={"Origin": "https://app.example.test"})
    assert bootstrap.status_code == 200
    assert bootstrap.json()["needs_refresh"] is True
    assert bootstrap.json()["csrf_token"] == initial["csrf_token"]
    assert "access_token" not in bootstrap.json()
    refreshed = await client.post("/api/auth/refresh", headers={
        "Origin": "https://app.example.test", "X-CSRF-Token": bootstrap.json()["csrf_token"],
    })
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] == ""
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_refresh_never_extends_absolute_expiry_and_rejects_expired_sessions(session_client):
    client, sessionmaker = session_client
    data = (await _signin(client)).json()
    from bebshax.auth.models import AuthSessions
    async with sessionmaker() as session:
        row = (await session.execute(select(AuthSessions))).scalar_one()
        row.absolute_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    assert (await client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})).status_code == 401
    assert (await client.get("/api/auth/me", headers=_bearer(data["access_token"]))).status_code == 401


async def test_concurrent_refresh_has_one_winner_and_replay_revokes_winner(session_client):
    client, _sessionmaker = session_client
    data = (await _signin(client)).json()
    responses = await asyncio.gather(*[
        client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
        for _attempt in range(2)
    ])
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response.json() for response in responses if response.status_code == 200)
    assert (await client.get("/api/auth/me", headers=_bearer(winner["access_token"]))).status_code == 401


async def test_access_only_refresh_is_bounded_and_cannot_mint_refresh_secrets(session_client):
    client, _sessionmaker = session_client
    data = (await _signin(client)).json()
    original = security.decode_access_token(data["access_token"])
    response = await client.post("/api/auth/refresh", headers=_bearer(data["access_token"]))
    assert response.status_code == 200
    claims = security.decode_access_token(response.json()["access_token"])
    assert claims["exp"] == original["exp"]
    assert response.json().get("refresh_token") is None


async def test_signed_jti_without_persisted_session_never_authenticates(session_client):
    client, _sessionmaker = session_client
    token = security.create_access_token("usr_session", session_id=str(secrets.token_hex(16)))
    assert (await client.get("/api/auth/me", headers=_bearer(token))).status_code == 401