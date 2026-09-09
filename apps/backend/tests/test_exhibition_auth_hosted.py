"""Hosted verification policy through local TestClient and SQLite only."""

import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from bebshax.api import auth as auth_api
from bebshax.api.limiter import limiter
from bebshax.auth import security
from bebshax.auth.models import EmailVerificationToken, Users
from bebshax.config import Settings
from bebshax.db.models import Base


_EMAIL = "hosted-auth@example.com"
_PASSWORD = "HostedPassword123!"


@pytest.fixture(params=["production", "staging"])
async def hosted_auth_client(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[TestClient]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'hosted_auth.db'}"
    settings = Settings(
        _env_file=None,
        environment=request.param,
        database_url=database_url,
        jwt_secret=secrets.token_urlsafe(48),
        jwt_secret_previous=None,
        require_email_verification=None,
        resend_api_key=secrets.token_urlsafe(32),
        email_from_address="noreply@example.com",
        smtp_host="",
        smtp_username=None,
        smtp_password=None,
        demo_mode=False,
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    verification_mail = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_api, "send_verification_email", verification_mail)
    limiter._limiter.storage.reset()
    auth_api._verify_failures.clear()

    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all, tables=[Users.__table__, EmailVerificationToken.__table__],
        )
    app = FastAPI()
    app.include_router(auth_api.auth_router)
    app.state.limiter = limiter
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
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
        json={"email": _EMAIL, "full_name": "Hosted Test User", "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_hosted_verification_gates_all_auth_paths_and_mints_current_sessions(
    hosted_auth_client: TestClient,
) -> None:
    signup = _signup(hosted_auth_client)
    user_id = signup["user"]["id"]
    prior_token = security.create_access_token(user_id)

    assert signup["verification_required"] is True
    assert signup["access_token"] == ""
    assert signup["user"]["is_verified"] is False
    assert hosted_auth_client.get("/api/auth/me", headers=_headers(prior_token)).status_code == 403
    assert hosted_auth_client.post("/api/auth/refresh", headers=_headers(prior_token)).status_code == 403
    assert hosted_auth_client.get("/optional-auth", headers=_headers(prior_token)).json() == {
        "user_id": None,
    }
    assert hosted_auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD},
    ).status_code == 403

    otp_code = hosted_auth_client.app.state.verification_mail.call_args.kwargs["otp_code"]
    verified = hosted_auth_client.post(
        "/api/auth/verify-email", json={"email": _EMAIL, "token": otp_code},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_required"] is False
    assert verified.json()["user"]["is_verified"] is True
    verified_token = verified.json()["access_token"]
    assert security.decode_access_token(verified_token)["session_version"] == 1
    assert hosted_auth_client.get("/api/auth/me", headers=_headers(verified_token)).status_code == 200
    assert hosted_auth_client.get("/optional-auth", headers=_headers(verified_token)).json() == {
        "user_id": user_id,
    }
    assert hosted_auth_client.post("/api/auth/refresh", headers=_headers(prior_token)).status_code == 401

    signin = hosted_auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD},
    )
    assert signin.status_code == 200, signin.text
    signin_token = signin.json()["access_token"]
    assert security.decode_access_token(signin_token)["session_version"] == 1
    refreshed = hosted_auth_client.post("/api/auth/refresh", headers=_headers(signin_token))
    assert refreshed.status_code == 200, refreshed.text
    assert security.decode_access_token(refreshed.json()["access_token"])["session_version"] == 1


def test_hosted_email_delivery_failure_never_grants_a_signup_session(
    hosted_auth_client: TestClient,
) -> None:
    hosted_auth_client.app.state.verification_mail.side_effect = RuntimeError("Test delivery failure")

    signup = _signup(hosted_auth_client)

    assert signup["verification_required"] is True
    assert signup["access_token"] == ""
    assert signup["user"]["is_verified"] is False
    assert hosted_auth_client.post(
        "/api/auth/signin", json={"email": _EMAIL, "password": _PASSWORD},
    ).status_code == 403