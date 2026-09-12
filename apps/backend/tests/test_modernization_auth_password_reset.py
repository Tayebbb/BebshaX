"""Local password recovery must change the authority used by local sign-in."""

import re
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bebshax.api import auth as auth_api
from bebshax.auth import email as auth_email, security
from bebshax.auth.models import EmailVerificationToken, Users
from bebshax.config import Settings
from bebshax.db.models import Base


@pytest.fixture
async def reset_client(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, jwt_secret=secrets.token_urlsafe(48),
        environment="development", require_email_verification=True,
        frontend_base_url="https://app.example.test", resend_api_key=None,
        smtp_username=None, smtp_password=None,
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api.limiter, "enabled", False)
    mail = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_email, "send_email", mail)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reset.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        session.add(Users(
            id="usr_reset", email="owner@example.test", full_name="Reset Owner",
            hashed_password=security.hash_password("Original123!"),
            is_verified=True, is_active=True, auth_provider="email",
        ))
        await session.commit()
    app = FastAPI()
    app.include_router(auth_api.auth_router)
    app.state.db_sessionmaker = sessionmaker
    async with AsyncClient(transport=ASGITransport(app), base_url="https://api.example.test") as client:
        yield client, sessionmaker, mail
    await engine.dispose()


async def _request_code(client, mail, email="owner@example.test"):
    response = await client.post("/api/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    return re.search(r"(?<!\d)(\d{6})(?!\d)", mail.call_args.args[2]).group(1)


async def test_reset_changes_local_password_and_revokes_old_bearer(reset_client):
    client, sessionmaker, mail = reset_client
    legacy_token = security.create_access_token("usr_reset")
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})).status_code == 200
    code = await _request_code(client, mail)

    response = await client.post("/api/auth/reset-password", json={
        "email": " OWNER@example.test ", "otp": code, "password": "Replacement123!",
        "purpose": "forget-password",
    })

    assert response.status_code == 200
    async with sessionmaker() as session:
        user = await session.get(Users, "usr_reset")
        assert security.verify_password("Replacement123!", user.hashed_password)
        assert not security.verify_password("Original123!", user.hashed_password)
        assert user.session_version > 0
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})).status_code == 401
    signin = await client.post("/api/auth/signin", json={"email": "owner@example.test", "password": "Replacement123!"})
    assert signin.status_code == 200
    assert "access_token" not in response.json()


async def test_forgot_password_does_not_enumerate_accounts_or_delivery_failure(reset_client):
    client, sessionmaker, mail = reset_client
    known = await client.post("/api/auth/forgot-password", json={"email": "owner@example.test"})
    unknown = await client.post("/api/auth/request-password-reset", json={"email": "absent@example.test"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert mail.call_count == 1
    async with sessionmaker() as session:
        records = (await session.execute(select(EmailVerificationToken))).scalars().all()
        for record in records:
            record.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        await session.commit()
    mail.side_effect = RuntimeError("Synthetic delivery failure")
    failed = await client.post("/api/auth/forgot-password", json={"email": "owner@example.test"})
    assert failed.status_code == known.status_code
    assert failed.json() == known.json()


async def test_reset_codes_are_purpose_bound_hashed_and_single_use(reset_client):
    client, sessionmaker, mail = reset_client
    code = await _request_code(client, mail)
    async with sessionmaker() as session:
        record = (await session.execute(select(EmailVerificationToken))).scalar_one()
        assert record.token != code
        assert record.purpose == "forget-password"
    verification = await client.post("/api/auth/verify-email", json={"email": "owner@example.test", "token": code})
    assert verification.status_code == 400
    payload = {"email": "owner@example.test", "otp": code, "password": "Replacement123!"}
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 200
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400


async def test_foreign_and_expired_codes_cannot_reset_password(reset_client):
    client, sessionmaker, mail = reset_client
    code = await _request_code(client, mail)
    foreign = await client.post("/api/auth/reset-password", json={
        "email": "absent@example.test", "otp": code, "password": "Replacement123!",
    })
    async with sessionmaker() as session:
        record = (await session.execute(select(EmailVerificationToken))).scalar_one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    expired = await client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "Replacement123!",
    })
    assert foreign.status_code == expired.status_code == 400
    assert foreign.json() == expired.json()


async def test_five_wrong_codes_lock_challenge_in_database(reset_client):
    client, sessionmaker, mail = reset_client
    code = await _request_code(client, mail)
    wrong = "000000" if code != "000000" else "111111"
    payload = {"email": "owner@example.test", "otp": wrong, "password": "Replacement123!"}
    for _attempt in range(5):
        assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400
    payload["otp"] = code
    assert (await client.post("/api/auth/reset-password", json=payload)).status_code == 400
    async with sessionmaker() as session:
        record = (await session.execute(select(EmailVerificationToken))).scalar_one()
        assert record.failed_attempts == 5


async def test_verification_otp_cannot_be_used_for_password_reset(reset_client):
    client, sessionmaker, _mail = reset_client
    async with sessionmaker() as session:
        session.add(EmailVerificationToken(
            user_id="usr_reset", token="123456",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        await session.commit()
    response = await client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": "123456", "password": "Replacement123!",
    })
    assert response.status_code == 400