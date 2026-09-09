"""Authentication contracts exercised through the real router and SQLite."""

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from bebshax.api import auth as auth_api
from bebshax.api.limiter import limiter
from bebshax.auth import security
from bebshax.auth.models import Users
from bebshax.config import Settings
from bebshax.db.models import Base


_EMAIL = "session-owner@example.com"
_PASSWORD = "Authentication123!"


@pytest.fixture
async def auth_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TestClient]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'auth_sessions.db'}"
    settings = Settings(
        _env_file=None,
        environment="development",
        database_url=database_url,
        jwt_secret=secrets.token_urlsafe(48),
        jwt_secret_previous=None,
        require_email_verification=True,
        resend_api_key=None,
        smtp_host="",
        smtp_username=None,
        smtp_password=None,
        email_from_address="",
        neon_auth_url="https://neon.invalid/auth",
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    verification_mail = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_api, "send_verification_email", verification_mail)
    limiter._limiter.storage.reset()
    auth_api._verify_failures.clear()

    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.include_router(auth_api.auth_router)
    app.state.limiter = limiter
    app.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.auth_test_settings = settings
    app.state.verification_mail = verification_mail

    @app.get("/optional-auth")
    async def optional_auth(
        current_user: Users | None = Depends(auth_api.get_optional_current_user),
    ) -> dict[str, str | None]:
        return {"user_id": current_user.id if current_user else None}

    try:
        with TestClient(app) as client:
            yield client
    finally:
        await engine.dispose()
        limiter._limiter.storage.reset()
        auth_api._verify_failures.clear()


def _signup(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/signup",
        json={
            "email": _EMAIL,
            "full_name": "Session Owner",
            "password": _PASSWORD,
            "auth_provider": "neon",
            "is_verified": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _verify_email(client: TestClient) -> dict:
    otp_code = client.app.state.verification_mail.call_args.kwargs["otp_code"]
    response = client.post("/api/auth/verify-email", json={"email": _EMAIL, "token": otp_code})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_signup_with_required_verification_returns_no_session(auth_client: TestClient):
    signup = _signup(auth_client)

    assert signup["verification_required"] is True
    assert signup["access_token"] == ""
    assert signup["token_type"] == "bearer"
    assert signup["user"]["is_verified"] is False
    assert signup["user"]["auth_provider"] == "email"


@pytest.mark.parametrize("provider", ["email", "neon", "google"])
@pytest.mark.parametrize("method,path", [("GET", "/api/auth/me"), ("POST", "/api/auth/refresh")])
async def test_unverified_token_cannot_authenticate_or_refresh(
    auth_client: TestClient, provider: str, method: str, path: str,
):
    signup = _signup(auth_client)
    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.auth_provider = provider
        await session.commit()
    token = security.create_access_token(signup["user"]["id"])

    response = auth_client.request(method, path, headers=_headers(token))

    assert response.status_code == 403


@pytest.mark.parametrize("provider", ["email", "neon", "google"])
async def test_optional_auth_does_not_identify_an_unverified_user(
    auth_client: TestClient, provider: str,
):
    signup = _signup(auth_client)
    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.auth_provider = provider
        await session.commit()
    token = security.create_access_token(signup["user"]["id"])

    response = auth_client.get("/optional-auth", headers=_headers(token))

    assert response.status_code == 200
    assert response.json() == {"user_id": None}


def test_signin_requires_verification_when_enforced(auth_client: TestClient):
    _signup(auth_client)

    response = auth_client.post("/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD})

    assert response.status_code == 403
    assert "access_token" not in response.json()


def test_email_verification_and_signin_issue_usable_sessions(auth_client: TestClient):
    signup = _signup(auth_client)

    verified = _verify_email(auth_client)

    assert verified["detail"] == "Email verified successfully."
    assert verified["verification_required"] is False
    assert verified["user"]["id"] == signup["user"]["id"]
    assert verified["user"]["is_verified"] is True
    assert auth_client.get("/api/auth/me", headers=_headers(verified["access_token"])).status_code == 200
    assert auth_client.get("/optional-auth", headers=_headers(verified["access_token"])).json() == {
        "user_id": signup["user"]["id"],
    }
    signin = auth_client.post("/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD})
    assert signin.status_code == 200
    assert auth_client.post(
        "/api/auth/refresh", headers=_headers(signin.json()["access_token"]),
    ).status_code == 200


async def test_email_verification_cannot_issue_a_session_for_a_disabled_user(auth_client: TestClient):
    signup = _signup(auth_client)
    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.is_active = False
        await session.commit()
    otp_code = auth_client.app.state.verification_mail.call_args.kwargs["otp_code"]

    response = auth_client.post("/api/auth/verify-email", json={"email": _EMAIL, "token": otp_code})

    assert response.status_code == 403
    assert "access_token" not in response.json()


def test_development_without_email_credentials_still_allows_sessions(auth_client: TestClient):
    auth_client.app.state.auth_test_settings.require_email_verification = None

    signup = _signup(auth_client)

    assert signup["verification_required"] is False
    assert signup["access_token"]
    assert auth_client.get("/api/auth/me", headers=_headers(signup["access_token"])).status_code == 200
    assert auth_client.post("/api/auth/refresh", headers=_headers(signup["access_token"])).status_code == 200
    assert auth_client.get("/optional-auth", headers=_headers(signup["access_token"])).json() == {
        "user_id": signup["user"]["id"],
    }
    assert auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD},
    ).status_code == 200


def test_wrong_verification_code_does_not_issue_a_session(auth_client: TestClient):
    _signup(auth_client)

    response = auth_client.post("/api/auth/verify-email", json={"email": _EMAIL, "token": "000000"})

    assert response.status_code == 400
    assert "access_token" not in response.json()


@pytest.fixture
def neon_identity(monkeypatch: pytest.MonkeyPatch) -> dict:
    identity = {
        "user": {
            "id": "neon-session-owner",
            "email": _EMAIL,
            "name": "Verified Session Owner",
            "emailVerified": True,
        },
    }

    def verify_session(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://neon.invalid/auth/get-session"
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer verified-neon-session"
        return httpx.Response(200, json=identity)

    original_client = httpx.AsyncClient

    def neon_client(*args, **kwargs) -> httpx.AsyncClient:
        return original_client(*args, transport=httpx.MockTransport(verify_session), **kwargs)

    monkeypatch.setattr(auth_api.httpx, "AsyncClient", neon_client)
    return identity


def _sync(client: TestClient, provider: str = "neon") -> dict:
    response = client.post(
        "/api/auth/sync",
        json={"neon_token": "verified-neon-session", "auth_provider": provider},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _signed_token(user_id: str, session_version: object = ...) -> str:
    token = security.create_access_token(user_id)
    header = token.split(".")[0]
    claims = security.decode_access_token(token)
    assert claims is not None
    if session_version is ...:
        claims.pop("session_version", None)
    else:
        claims["session_version"] = session_version
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signature = hmac.new(
        security.get_settings().jwt_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{encoded_signature}"


def _assert_session_rejected(client: TestClient, token: str) -> None:
    profile = client.get("/api/auth/me", headers=_headers(token))
    assert profile.status_code == 401
    refreshed = client.post("/api/auth/refresh", headers=_headers(token))
    assert refreshed.status_code == 401
    assert client.get("/optional-auth", headers=_headers(token)).json() == {"user_id": None}


def test_new_tokens_include_the_initial_session_version(auth_client: TestClient):
    auth_client.app.state.auth_test_settings.require_email_verification = False

    signup = _signup(auth_client)

    assert security.decode_access_token(signup["access_token"])["session_version"] == 0


def test_token_creation_supports_an_explicit_session_version(auth_client: TestClient):
    token = security.create_access_token("usr_versioned", session_version=7)

    assert security.decode_access_token(token)["session_version"] == 7


@pytest.mark.parametrize("version", [None, -1, True, False, 0.0, "0", [], {}, 1])
def test_invalid_or_mismatched_session_version_cannot_authenticate(
    auth_client: TestClient, version: object,
):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    token = _signed_token(signup["user"]["id"], version)

    _assert_session_rejected(auth_client, token)


async def test_legacy_token_only_works_before_the_first_password_reset(auth_client: TestClient):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    legacy_token = _signed_token(signup["user"]["id"])
    assert auth_client.get("/api/auth/me", headers=_headers(legacy_token)).status_code == 200
    assert auth_client.post("/api/auth/refresh", headers=_headers(legacy_token)).status_code == 200
    assert auth_client.get("/optional-auth", headers=_headers(legacy_token)).json() == {
        "user_id": signup["user"]["id"],
    }

    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.hashed_password = security.hash_password("Replacement456!")
        await session.commit()

    _assert_session_rejected(auth_client, legacy_token)


async def test_password_reset_revokes_all_old_sessions_and_new_signin_uses_current_version(
    auth_client: TestClient,
):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    refreshed = auth_client.post("/api/auth/refresh", headers=_headers(signup["access_token"])).json()
    replacement = "Replacement456!"

    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.hashed_password = security.hash_password(replacement)
        await session.commit()

    _assert_session_rejected(auth_client, signup["access_token"])
    _assert_session_rejected(auth_client, refreshed["access_token"])
    assert auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD},
    ).status_code == 401
    signin = auth_client.post("/api/auth/signin", json={"email": _EMAIL, "password": replacement})
    assert signin.status_code == 200
    new_token = signin.json()["access_token"]
    assert security.decode_access_token(new_token)["session_version"] == 1
    assert auth_client.get("/api/auth/me", headers=_headers(new_token)).status_code == 200
    assert auth_client.get("/optional-auth", headers=_headers(new_token)).json() == {
        "user_id": signup["user"]["id"],
    }
    refreshed = auth_client.post("/api/auth/refresh", headers=_headers(new_token))
    assert refreshed.status_code == 200
    assert security.decode_access_token(refreshed.json()["access_token"])["session_version"] == 1


async def test_password_resets_from_stale_orm_snapshots_do_not_lose_revocations(auth_client: TestClient):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    sessions = auth_client.app.state.db_sessionmaker
    async with sessions() as first_session, sessions() as second_session:
        first_user = await first_session.get(Users, signup["user"]["id"])
        second_user = await second_session.get(Users, signup["user"]["id"])
        first_user.hashed_password = security.hash_password("FirstReplacement456!")
        await first_session.commit()
        first_signin = auth_client.post(
            "/api/auth/signin", json={"email": _EMAIL, "password": "FirstReplacement456!"},
        )
        assert first_signin.status_code == 200

        second_user.hashed_password = security.hash_password("SecondReplacement789!")
        await second_session.commit()

    _assert_session_rejected(auth_client, first_signin.json()["access_token"])
    second_signin = auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": "SecondReplacement789!"},
    )
    assert second_signin.status_code == 200
    assert security.decode_access_token(second_signin.json()["access_token"])["session_version"] == 2


@pytest.mark.parametrize("provider", ["email", "neon", "google"])
@pytest.mark.parametrize("verified_local", [False, True])
def test_identity_link_revokes_prior_sessions_regardless_of_client_provider(
    auth_client: TestClient, neon_identity: dict, provider: str, verified_local: bool,
):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    previous = _verify_email(auth_client) if verified_local else signup
    legacy_token = _signed_token(signup["user"]["id"])
    auth_client.app.state.auth_test_settings.require_email_verification = True

    linked = _sync(auth_client, provider)

    assert linked["user"]["id"] == signup["user"]["id"]
    _assert_session_rejected(auth_client, previous["access_token"])
    _assert_session_rejected(auth_client, legacy_token)
    assert linked["user"]["auth_provider"] == "neon"
    assert linked["user"]["is_verified"] is True
    assert auth_client.get("/api/auth/me", headers=_headers(linked["access_token"])).status_code == 200
    assert auth_client.get("/optional-auth", headers=_headers(linked["access_token"])).json() == {
        "user_id": signup["user"]["id"],
    }
    refreshed = auth_client.post("/api/auth/refresh", headers=_headers(linked["access_token"]))
    assert refreshed.status_code == 200
    assert security.decode_access_token(refreshed.json()["access_token"])["session_version"] == (
        security.decode_access_token(linked["access_token"])["session_version"]
    )
    signin = auth_client.post("/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD})
    assert signin.status_code == (200 if verified_local else 401)


def test_refresh_cannot_extend_a_pre_link_signup_token(auth_client: TestClient, neon_identity: dict):
    auth_client.app.state.auth_test_settings.require_email_verification = False
    signup = _signup(auth_client)
    auth_client.app.state.auth_test_settings.require_email_verification = True
    _sync(auth_client, "email")

    response = auth_client.post("/api/auth/refresh", headers=_headers(signup["access_token"]))

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_repeated_verified_sync_keeps_current_sessions_valid(auth_client: TestClient, neon_identity: dict):
    first_sync = _sync(auth_client, "email")
    neon_identity["user"]["name"] = "Updated Display Name"

    second_sync = _sync(auth_client, "google")

    assert second_sync["user"]["auth_provider"] == "neon"
    assert second_sync["user"]["full_name"] == "Updated Display Name"
    assert auth_client.get("/api/auth/me", headers=_headers(first_sync["access_token"])).status_code == 200


@pytest.mark.parametrize("email_verified", ["false", "true", 1, None, False])
def test_sync_requires_a_literal_verified_boolean_from_neon(
    auth_client: TestClient, neon_identity: dict, email_verified: object,
):
    neon_identity["user"]["emailVerified"] = email_verified

    response = auth_client.post(
        "/api/auth/sync", json={"neon_token": "verified-neon-session", "auth_provider": "email"},
    )

    assert response.status_code == 401
    assert "access_token" not in response.json()


async def test_sync_cannot_issue_a_session_for_a_disabled_user(auth_client: TestClient, neon_identity: dict):
    signup = _signup(auth_client)
    async with auth_client.app.state.db_sessionmaker() as session:
        user = await session.get(Users, signup["user"]["id"])
        user.is_active = False
        await session.commit()

    response = auth_client.post("/api/auth/sync", json={"neon_token": "verified-neon-session"})

    assert response.status_code == 403
    assert "access_token" not in response.json()