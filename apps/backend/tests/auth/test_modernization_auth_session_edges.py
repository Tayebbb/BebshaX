"""Session revocation ordering, older-generation replay, and rejected-token admission."""

import asyncio
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from bebshax.api import auth as auth_api
from bebshax.api import limiter as rate_api
from bebshax.auth import sessions
from bebshax.auth.models import AuthSessions
from bebshax.auth.security import create_access_token
from bebshax.auth.transport import REFRESH_COOKIE


async def _signin(state) -> dict:
    response = await state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    })
    assert response.status_code == 200
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_older_generation_replay_revokes_only_its_family(identity_state):
    first = await _signin(identity_state)
    independent = await _signin(identity_state)
    current = first
    for generation in range(2):
        response = await identity_state.client.post("/api/auth/refresh", json={"refresh_token": current["refresh_token"]})
        assert response.status_code == 200
        current = response.json()
        assert current["session_expires_at"] == first["session_expires_at"]
    replay = await identity_state.client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401
    assert (await identity_state.client.get("/api/auth/me", headers=_bearer(current["access_token"]))).status_code == 401
    assert (await identity_state.client.get("/api/auth/me", headers=_bearer(independent["access_token"]))).status_code == 200


async def test_guessed_secret_with_known_session_id_does_not_revoke_victim(identity_state):
    issued = await _signin(identity_state)
    token = issued["refresh_token"]
    wrong = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert (await identity_state.client.post("/api/auth/refresh", json={"refresh_token": wrong})).status_code == 401
    assert (await identity_state.client.get("/api/auth/me", headers=_bearer(issued["access_token"]))).status_code == 200


async def test_logout_accepts_refresh_proof_when_stale_access_is_also_attached(identity_state):
    issued = await _signin(identity_state)
    expired = create_access_token("usr_identity", expires_delta=timedelta(seconds=-1))
    response = await identity_state.client.post("/api/auth/logout", json={
        "refresh_token": issued["refresh_token"],
    }, headers=_bearer(expired))
    assert response.status_code == 200
    assert (await identity_state.client.get("/api/auth/me", headers=_bearer(issued["access_token"]))).status_code == 401


@pytest.mark.parametrize("proof", ["access", "refresh"])
@pytest.mark.parametrize("intervening_action", ["logout", "refresh"])
async def test_logout_all_rechecks_proof_after_acquiring_user_lock(
    identity_state, monkeypatch, proof, intervening_action,
) -> None:
    state = identity_state
    issued = await _signin(state)
    independent = await _signin(state)
    waiting = asyncio.Event()
    release = asyncio.Event()
    original_lock = auth_api.lock_user

    async def pause_first_lock(session, user_id):
        if not waiting.is_set():
            waiting.set()
            await release.wait()
        return await original_lock(session, user_id)

    monkeypatch.setattr(auth_api, "lock_user", pause_first_lock)
    kwargs = (
        {"headers": _bearer(issued["access_token"])}
        if proof == "access" else {"json": {"refresh_token": issued["refresh_token"]}}
    )
    pending = asyncio.create_task(state.client.post("/api/auth/logout-all", **kwargs))
    try:
        async with asyncio.timeout(10):
            await waiting.wait()
            revoked = await state.client.post(
                f"/api/auth/{intervening_action}", json={"refresh_token": issued["refresh_token"]},
            )
            assert revoked.status_code == 200
            release.set()
            result = await pending
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)

    assert result.status_code == 401
    surviving = await state.client.get("/api/auth/me", headers=_bearer(independent["access_token"]))
    assert surviving.status_code == 200


async def test_invalid_refresh_credentials_still_consume_ip_budget(identity_state, monkeypatch):
    monkeypatch.setitem(rate_api.AUTH_RATE_POLICIES, "refresh", rate_api.AuthRatePolicy(2, 60, 30, 60))
    results = [
        await identity_state.client.post("/api/auth/refresh", json={"refresh_token": "f" * 32 + "." + "a" * 43})
        for attempt in range(3)
    ]
    assert [response.status_code for response in results] == [401, 401, 429]


@pytest.mark.parametrize("action", ["logout", "reset"])
async def test_pending_revocation_cannot_be_escaped_by_inflight_refresh(identity_state, monkeypatch, action):
    state = identity_state
    issued = await _signin(state)
    if action == "reset":
        assert (await state.client.post("/api/auth/forgot-password", json={"email": "owner@example.test"})).status_code == 200
        code = state.reset_mail.call_args.args[1]
    locked = asyncio.Event()
    revocation_started = asyncio.Event()
    release = asyncio.Event()
    original_lock = sessions.lock_user
    original_limits = auth_api.enforce_auth_limits

    async def hold_rotation(session, user_id):
        result = await original_lock(session, user_id)
        locked.set()
        await release.wait()
        return result

    async def observe_revocation(request, session, selected_action, *args, **kwargs):
        if selected_action == action:
            revocation_started.set()
        return await original_limits(request, session, selected_action, *args, **kwargs)

    monkeypatch.setattr(sessions, "lock_user", hold_rotation)
    monkeypatch.setattr(auth_api, "enforce_auth_limits", observe_revocation)
    refresh_task = asyncio.create_task(state.client.post("/api/auth/refresh", json={"refresh_token": issued["refresh_token"]}))
    pending = None
    try:
        async with asyncio.timeout(10):
            await locked.wait()
            if action == "logout":
                pending = asyncio.create_task(state.client.post("/api/auth/logout", headers=_bearer(issued["access_token"])))
            else:
                pending = asyncio.create_task(state.client.post("/api/auth/reset-password", json={
                    "email": "owner@example.test", "otp": code, "password": "Replacement123!",
                }))
            await revocation_started.wait()
            release.set()
            refreshed, revoked = await asyncio.gather(refresh_task, pending)
    finally:
        release.set()
        await asyncio.gather(refresh_task, *([pending] if pending is not None else []), return_exceptions=True)
    assert refreshed.status_code == revoked.status_code == 200
    rotated = refreshed.json()
    assert (await state.client.get("/api/auth/me", headers=_bearer(rotated["access_token"]))).status_code == 401
    assert (await state.client.post("/api/auth/refresh", json={"refresh_token": rotated["refresh_token"]})).status_code == 401
    async with state.sessions() as session:
        records = (await session.scalars(select(AuthSessions).where(AuthSessions.family_id == issued["session_id"]))).all()
        assert records and all(record.revoked_at is not None for record in records)


async def test_url_bearer_is_not_a_backend_authentication_channel(identity_state):
    issued = await _signin(identity_state)
    response = await identity_state.client.get("/api/auth/me", params={"token": issued["access_token"]})
    assert response.status_code == 401


async def test_foreign_refresh_cookie_cannot_replace_browser_identity(identity_state):
    headers = {"X-Auth-Transport": "cookie", "Origin": "https://app.example.test"}
    initial = await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "Identity123!",
    }, headers=headers)
    assert initial.status_code == 200
    async with AsyncClient(
        transport=ASGITransport(identity_state.app), base_url="https://api.example.test",
    ) as other:
        response = await other.post("/api/auth/signin", json={
            "email": "other@example.test", "password": "Identity123!",
        }, headers=headers)
        assert response.status_code == 200
        foreign_refresh = other.cookies.get(REFRESH_COOKIE)
    identity_state.client.cookies.set(REFRESH_COOKIE, foreign_refresh, domain="api.example.test", path="/api/auth")
    result = await identity_state.client.get("/api/auth/session", headers={"Origin": "https://app.example.test"})
    assert result.status_code == 401
    me = await identity_state.client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == "usr_identity"