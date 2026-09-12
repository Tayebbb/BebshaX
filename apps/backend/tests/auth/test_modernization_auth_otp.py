"""OTP storage, purpose, credential authority, and single-use transaction regressions."""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from bebshax.auth.models import EmailVerificationToken, Users
from bebshax.auth import security


async def _signup(state, email: str) -> str:
    result = await state.client.post("/api/auth/signup", json={
        "email": email, "full_name": "Synthetic Registrant", "password": "Identity123!",
    })
    assert result.status_code == 201
    return state.verification_mail.call_args.kwargs["otp_code"]


async def _reset_code(state) -> str:
    result = await state.client.post("/api/auth/forgot-password", json={"email": "owner@example.test"})
    assert result.status_code == 200
    return state.reset_mail.call_args.args[1]


async def test_verification_otp_is_hashed_and_expires_within_fifteen_minutes(identity_state):
    code = await _signup(identity_state, "new@example.test")
    async with identity_state.sessions() as session:
        record = (await session.scalars(select(EmailVerificationToken))).one()
        assert record.token != code
        assert len(record.token) == 64
        assert record.purpose == "email-verification"
        assert record.expires_at - record.created_at <= timedelta(minutes=15)


async def test_same_otp_value_for_different_accounts_does_not_collide(identity_state, monkeypatch):
    monkeypatch.setattr("secrets.randbelow", lambda bound: 123456)
    first = await _signup(identity_state, "first@example.test")
    second = await _signup(identity_state, "second@example.test")
    for email, code in (("first@example.test", first), ("second@example.test", second)):
        result = await identity_state.client.post("/api/auth/verify-email", json={"email": email, "token": code})
        assert result.status_code == 200


async def test_concurrent_verification_consumes_otp_exactly_once(identity_state):
    code = await _signup(identity_state, "new@example.test")
    replies = await asyncio.gather(*[
        identity_state.client.post("/api/auth/verify-email", json={"email": "new@example.test", "token": code})
        for attempt in range(2)
    ])
    assert sorted(reply.status_code for reply in replies) == [200, 400]
    async with identity_state.sessions() as session:
        user = (await session.scalars(select(Users).where(Users.email == "new@example.test"))).one()
        assert user.session_version == 1


async def test_verification_failures_are_persisted_on_the_challenge(identity_state):
    code = await _signup(identity_state, "new@example.test")
    wrong = "000000" if code != "000000" else "111111"
    for attempt in range(2):
        reply = await identity_state.client.post("/api/auth/verify-email", json={"email": "new@example.test", "token": wrong})
        assert reply.status_code == 400
    async with identity_state.sessions() as session:
        record = (await session.scalars(select(EmailVerificationToken))).one()
        assert record.failed_attempts == 2


async def test_resend_cannot_reset_an_exhausted_verification_budget(identity_state):
    code = await _signup(identity_state, "new@example.test")
    wrong = "000000" if code != "000000" else "111111"
    for attempt in range(5):
        reply = await identity_state.client.post("/api/auth/verify-email", json={"email": "new@example.test", "token": wrong})
        assert reply.status_code == 400
    reply = await identity_state.client.post("/api/auth/resend-verification", json={"email": "new@example.test"})
    assert reply.status_code == 200
    assert identity_state.verification_mail.call_count == 1


async def test_reset_keeps_local_password_authority_for_neon_linked_accounts(identity_state):
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.auth_provider = "neon"
        await session.commit()
    signin = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    })
    assert signin.status_code == 200
    issued = signin.json()
    code = await _reset_code(identity_state)
    changed = await identity_state.client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "Replacement123!",
        "purpose": "forget-password",
    })
    assert changed.status_code == 200
    assert (await identity_state.client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {issued['access_token']}",
    })).status_code == 401
    assert (await identity_state.client.post("/api/auth/refresh", json={
        "refresh_token": issued["refresh_token"],
    })).status_code == 401
    for password, expected_status in (("Identity123!", 401), ("Replacement123!", 200)):
        result = await identity_state.client.post("/api/auth/signin", json={"email": "owner@example.test", "password": password})
        assert result.status_code == expected_status


async def test_credential_change_invalidates_outstanding_reset_challenge(identity_state):
    code = await _reset_code(identity_state)
    replacement = security.hash_password("SeparateChange123!")
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.hashed_password = replacement
        await session.commit()
    replay = await identity_state.client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "AttackerChoice123!",
    })
    assert replay.status_code == 400
    async with identity_state.sessions() as session:
        assert (await session.get(Users, "usr_identity")).hashed_password == replacement


async def test_concurrent_reset_commits_only_one_password_change(identity_state):
    code = await _reset_code(identity_state)
    replies = await asyncio.gather(*[
        identity_state.client.post("/api/auth/reset-password", json={
            "email": "owner@example.test", "otp": code, "password": "Replacement123!",
        })
        for attempt in range(2)
    ])
    assert sorted(reply.status_code for reply in replies) == [200, 400]


async def test_expired_code_and_wrong_purpose_leave_account_unchanged(identity_state):
    code = await _reset_code(identity_state)
    wrong_purpose = await identity_state.client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "Replacement123!",
        "purpose": "email-verification",
    })
    assert wrong_purpose.status_code == 422
    async with identity_state.sessions() as session:
        record = (await session.scalars(select(EmailVerificationToken))).one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    expired = await identity_state.client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "Replacement123!",
    })
    assert expired.status_code == 400


async def test_unverified_recovery_proves_email_and_uses_the_new_password(identity_state):
    async with identity_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.is_verified = False
        await session.commit()
    code = await _reset_code(identity_state)
    result = await identity_state.client.post("/api/auth/reset-password", json={
        "email": "owner@example.test", "otp": code, "password": "Replacement123!",
    })
    assert result.status_code == 200
    signin = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Replacement123!",
    })
    assert signin.status_code == 200
    assert signin.json()["user"]["is_verified"] is True