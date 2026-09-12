"""Bounded auth input, uniform account replies, and transport edge conditions."""

import threading
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from bebshax.api import auth as auth_api
from bebshax.auth import security, service
from bebshax.auth.models import Users


async def test_signup_is_uniform_for_new_existing_and_disabled_accounts(identity_state):
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_other")
        user.is_active = False
        await session.commit()
    replies = [
        await identity_state.client.post("/api/auth/signup", json={
            "email": email, "full_name": "Supplied Name", "password": "Identity123!",
        })
        for email in ("new@example.test", "owner@example.test", "other@example.test")
    ]
    assert [reply.status_code for reply in replies] == [201, 201, 201]
    assert replies[0].json() == replies[1].json() == replies[2].json()
    pending = replies[0].json()
    assert pending["verification_required"] is True
    assert pending["access_token"] == ""
    assert pending["refresh_token"] is None
    assert pending["user"] is None


async def test_unverified_accounts_cannot_bypass_email_proof_with_legacy_setting(identity_state):
    identity_state.settings.require_email_verification = False
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.is_verified = False
        await session.commit()
    response = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    })
    assert response.status_code == 403
    assert "access_token" not in response.json()


async def test_first_unknown_and_known_signin_do_equal_hash_work(identity_state, monkeypatch):
    original = security.hashlib.pbkdf2_hmac
    work = []

    def count_work(*args, **kwargs):
        work.append(args[3])
        return original(*args, **kwargs)

    monkeypatch.setattr(security.hashlib, "pbkdf2_hmac", count_work)
    costs = []
    for email in ("owner@example.test", "absent@example.test"):
        service._dummy_hash.cache_clear()
        before = len(work)
        response = await identity_state.client.post("/api/auth/signin", json={
            "email": email, "password": "WrongPassword123!",
        })
        assert response.status_code == 401
        costs.append(work[before:])
    assert costs[0] == costs[1]


async def test_password_verification_runs_off_the_event_loop(identity_state, monkeypatch):
    original = service.verify_password
    threads = []
    event_loop_thread = threading.get_ident()

    def tracked_verify(plain, hashed):
        threads.append(threading.get_ident())
        return original(plain, hashed)

    monkeypatch.setattr(service, "verify_password", tracked_verify)
    for email in ("owner@example.test", "absent@example.test"):
        response = await identity_state.client.post("/api/auth/signin", json={
            "email": email, "password": "WrongPassword123!",
        })
        assert response.status_code == 401
    assert len(threads) == 2
    assert all(thread != event_loop_thread for thread in threads)


async def test_malformed_password_record_still_performs_dummy_verification(identity_state, monkeypatch):
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_other")
        user.hashed_password = "malformed-local-hash"
        await session.commit()
    service._dummy_hash()
    original = security.hashlib.pbkdf2_hmac
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(security.hashlib, "pbkdf2_hmac", counted)
    response = await identity_state.client.post("/api/auth/signin", json={
        "email": "other@example.test", "password": "WrongPassword123!",
    })
    assert response.status_code == 401
    assert len(calls) == 1


@pytest.mark.parametrize("model,payload", [
    (auth_api.SignInRequest, {"email": "owner@example.test", "password": "p" * 129}),
    (auth_api.SignInRequest, {"email": "a" * 255 + "@example.test", "password": "Identity123!"}),
    (auth_api.SignUpRequest, {"email": "owner@example.test", "password": "Identity123!", "full_name": " " * 5}),
    (auth_api.UserSyncRequest, {"neon_token": "n" * 8193}),
    (auth_api.UserSyncRequest, {"neon_token": "signed-by-idp", "role": "developer"}),
    (auth_api.VerifyEmailRequest, {"email": "owner@example.test", "token": "1234567"}),
    (auth_api.ResetPasswordRequest, {"email": "owner@example.test", "otp": "123456", "password": "p" * 129}),
    (auth_api.ResetPasswordRequest, {"email": "owner@example.test", "otp": "123456", "password": "Identity123!", "purpose": "email-verification"}),
    (auth_api.ResendVerificationRequest, {"email": "not an address"}),
    (auth_api.RefreshRequest, {"refresh_token": "r" * 4096}),
])
def test_auth_input_is_rejected_at_bounded_schema(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


async def test_auth_validation_does_not_echo_rejected_values_or_field_names(identity_state):
    sentinel = "private-auth-sentinel"
    response = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": sentinel * 100, sentinel: "extra",
    })
    assert response.status_code == 422
    assert sentinel not in response.text
    assert response.headers["cache-control"] == "no-store"


async def test_non_ascii_csrf_header_is_denied_without_server_error(identity_state):
    signin = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    }, headers={"X-Auth-Transport": "cookie", "Origin": "https://app.example.test"})
    assert signin.status_code == 200
    result = await identity_state.client.post("/optional-private", headers=[
        (b"Origin", b"https://app.example.test"), (b"X-CSRF-Token", b"\xff" * 64),
    ])
    assert result.status_code == 403


async def test_cookie_login_on_plain_http_is_rejected(identity_state):
    result = await identity_state.client.post("http://api.example.test/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    }, headers={"X-Auth-Transport": "cookie", "Origin": "https://app.example.test"})
    assert result.status_code == 403
    assert not result.headers.get_list("set-cookie")


@pytest.mark.parametrize("invalid", [
    {"email": {"unexpected": "object"}},
    {"email": "e" * 255 + "@example.test"},
    {"name": ["not", "a", "name"]},
    {"name": "n" * 101},
    {"image": "https://example.test/" + "i" * 513},
    {"image": "javascript:alert(1)"},
])
async def test_neon_profile_is_validated_before_account_mutation(identity_state, monkeypatch, invalid):
    monkeypatch.setattr(auth_api, "verify_neon_token", AsyncMock(return_value={
        "user": {"email": "owner@example.test", "name": "Verified Identity", "emailVerified": True, **invalid},
    }))
    response = await identity_state.client.post("/api/auth/sync", json={"neon_token": "synthetic-idp-session"})
    assert response.status_code == 401
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        assert user.full_name == "Synthetic Owner"
        assert user.auth_provider == "email"


async def test_neon_profile_cannot_promote_role_or_choose_local_user_id(identity_state, monkeypatch):
    monkeypatch.setattr(auth_api, "verify_neon_token", AsyncMock(return_value={
        "user": {
            "email": "owner@example.test", "name": "Verified Identity", "emailVerified": True,
            "role": "admin", "id": "usr_other",
        },
    }))
    response = await identity_state.client.post("/api/auth/sync", json={"neon_token": "synthetic-idp-session"})
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "usr_identity"
    assert response.json()["user"]["role"] == "user"


@pytest.mark.parametrize("replacement", [{"iat": -(2**70)}, {"nbf": int(time.time()) + 3600}])
def test_signed_time_claims_cannot_trigger_overflow_or_bypass_not_before(identity_state, replacement):
    token = security.create_access_token("usr_identity")
    header, body, signature = token.split(".")
    claims = json.loads(security._b64_decode(body))
    claims.update(replacement)
    body = security._b64_encode(json.dumps(claims).encode())
    signature = security._b64_encode(hmac.new(
        identity_state.settings.jwt_secret.encode(), f"{header}.{body}".encode(), hashlib.sha256,
    ).digest())
    assert security.decode_access_token(f"{header}.{body}.{signature}") is None