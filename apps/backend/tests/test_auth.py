"""Tests for Authentication: password hashing, JWT creation/validation, and API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from bebshax.auth.service import authenticate_user, create_user, get_user_by_email
from bebshax.db.models import Base
from bebshax.main import create_app


def test_password_hashing_and_verification():
    """Verify password hashing produces salted hashes and verifies correctly."""
    pwd = "SecurePassword123!"
    hashed = hash_password(pwd)
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_jwt_access_token_creation_and_decoding():
    """Verify JWT creation and claims decoding."""
    data = {"sub": "usr_test123", "email": "test@bebshax.com", "name": "Test User"}
    token = create_access_token(data)
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "usr_test123"
    assert decoded["email"] == "test@bebshax.com"
    assert decoded["name"] == "Test User"
    assert "exp" in decoded

    # Invalid token verification
    assert decode_access_token("invalid.token.structure") is None
    assert decode_access_token(token + "tampered") is None


@pytest.mark.asyncio
async def test_user_service_crud_and_auth(tmp_path):
    """Test user database service methods using in-memory SQLite."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test_auth.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sm() as session:
        user = await create_user(
            session=session,
            email="founder@company.com",
            full_name="Sarah Founder",
            password="StrongPassword88",
        )
        assert user.id.startswith("usr_")
        assert user.email == "founder@company.com"
        assert user.full_name == "Sarah Founder"
        assert user.hashed_password is not None

        # Lookup
        found = await get_user_by_email(session, "FOUNDER@company.com")
        assert found is not None
        assert found.id == user.id

        # Authenticate success
        auth_user = await authenticate_user(session, "founder@company.com", "StrongPassword88")
        assert auth_user is not None
        assert auth_user.id == user.id

        # Authenticate failure
        bad_user = await authenticate_user(session, "founder@company.com", "WrongPassword")
        assert bad_user is None


@pytest.mark.asyncio
async def test_auth_api_flow(monkeypatch, tmp_path):
    """Test HTTP signup, signin, and /me authenticated profile."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test_auth_api.db"
    monkeypatch.setenv("BEBSHAX_DATABASE_URL", db_url)

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()
    app.state.db_sessionmaker = sm
    app.state.sessionmaker = sm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Sign Up
        signup_res = await client.post(
            "/api/auth/signup",
            json={
                "email": "alex.rivera@fintech.io",
                "full_name": "Alex Rivera",
                "password": "Password1234!",
            },
        )
        assert signup_res.status_code == 201
        data = signup_res.json()
        assert "access_token" in data
        assert data["user"]["email"] == "alex.rivera@fintech.io"
        assert data["user"]["full_name"] == "Alex Rivera"
        token = data["access_token"]

        # Duplicate signup should conflict (409)
        dup_res = await client.post(
            "/api/auth/signup",
            json={
                "email": "alex.rivera@fintech.io",
                "full_name": "Alex Duplicate",
                "password": "Password1234!",
            },
        )
        assert dup_res.status_code == 409

        # 2. Sign In
        signin_res = await client.post(
            "/api/auth/signin",
            json={
                "email": "alex.rivera@fintech.io",
                "password": "Password1234!",
            },
        )
        assert signin_res.status_code == 200
        signin_data = signin_res.json()
        assert "access_token" in signin_data
        new_token = signin_data["access_token"]

        # Invalid password should fail (401)
        bad_signin = await client.post(
            "/api/auth/signin",
            json={
                "email": "alex.rivera@fintech.io",
                "password": "WrongPassword99",
            },
        )
        assert bad_signin.status_code == 401

        # 3. /me with Bearer token
        me_res = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == "alex.rivera@fintech.io"
        assert me_data["full_name"] == "Alex Rivera"

        # /me without token should fail (401)
        no_auth = await client.get("/api/auth/me")
        assert no_auth.status_code == 401

        # 4. Google Auth
        google_res = await client.post(
            "/api/auth/google",
            json={
                "email": "taylor.google@example.com",
                "name": "Taylor Google",
            },
        )
        assert google_res.status_code == 200
        g_data = google_res.json()
        assert "access_token" in g_data
        assert g_data["user"]["auth_provider"] == "google"
