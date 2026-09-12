"""Account and IP admission must survive worker changes and reject spoofed peers."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from bebshax.api import auth as auth_api
from bebshax.api import limiter as rate_api


async def test_account_budget_survives_distributed_ips_and_new_worker(identity_state):
    state = identity_state
    for attempt in range(5):
        async with AsyncClient(
            transport=ASGITransport(state.app, client=(f"192.0.2.{attempt + 1}", 50000)),
            base_url="https://api.example.test",
        ) as client:
            result = await client.post("/api/auth/signin", json={
                "email": "owner@example.test", "password": "WrongPassword123!",
            })
            assert result.status_code == 401
    engine = create_async_engine(state.database_url)
    new_worker = FastAPI()
    new_worker.include_router(auth_api.auth_router)
    new_worker.state.db_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with AsyncClient(
            transport=ASGITransport(new_worker, client=("198.51.100.10", 50000)),
            base_url="https://api.example.test",
        ) as client:
            result = await client.post("/api/auth/signin", json={
                "email": " OWNER@example.test ", "password": "Identity123!",
            })
        assert result.status_code == 429
        assert 0 < int(result.headers["retry-after"]) <= 900
    finally:
        await engine.dispose()


async def test_ip_budget_applies_across_different_accounts(identity_state, monkeypatch):
    from bebshax.api.limiter import AUTH_RATE_POLICIES, AuthRatePolicy

    monkeypatch.setitem(AUTH_RATE_POLICIES, "signin", AuthRatePolicy(2, 60, 5, 900))
    results = [
        await identity_state.client.post("/api/auth/signin", json={
            "email": f"absent-{attempt}@example.test", "password": "WrongPassword123!",
        })
        for attempt in range(3)
    ]
    assert [result.status_code for result in results] == [401, 401, 429]


async def test_denied_ip_does_not_allocate_or_charge_account_budgets(identity_state, monkeypatch) -> None:
    from bebshax.api.limiter import AUTH_RATE_POLICIES, AuthRatePolicy
    from bebshax.auth.models import AuthRateLimits

    monkeypatch.setitem(AUTH_RATE_POLICIES, "signin", AuthRatePolicy(2, 60, 5, 900))
    for attempt in range(5):
        result = await identity_state.client.post("/api/auth/signin", json={
            "email": f"absent-{attempt}@example.test", "password": "WrongPassword123!",
        })
        assert result.status_code == (401 if attempt < 2 else 429)

    async with identity_state.sessions() as session:
        rows = (await session.scalars(select(AuthRateLimits))).all()
    assert len(rows) == 3
    assert sorted(row.attempts for row in rows) == [1, 1, 3]


async def test_durable_budget_keys_do_not_store_raw_account_or_ip(identity_state):
    from bebshax.auth.models import AuthRateLimits

    await identity_state.client.post("/api/auth/signin", json={
        "email": "owner@example.test", "password": "WrongPassword123!",
    })
    async with identity_state.sessions() as session:
        rows = (await session.scalars(select(AuthRateLimits))).all()
    assert len(rows) == 2
    assert all(len(row.key) == 64 and int(row.key, 16) >= 0 for row in rows)
    assert all(row.attempts == 1 for row in rows)


def _peer(peer: str, forwarded: str) -> Request:
    return Request({
        "type": "http", "client": (peer, 50000),
        "headers": [(b"x-forwarded-for", forwarded.encode())],
    })


def test_forwarded_flag_without_proxy_allowlist_never_trusts_client_header(identity_state, monkeypatch):
    identity_state.settings.rate_limit_trust_forwarded_for = True
    monkeypatch.delenv("BEBSHAX_TRUSTED_PROXY_CIDRS", raising=False)
    assert rate_api._client_key(_peer("198.51.100.10", "203.0.113.40")) == "198.51.100.10"


def test_direct_untrusted_peer_cannot_spoof_forwarded_identity(identity_state, monkeypatch):
    identity_state.settings.rate_limit_trust_forwarded_for = True
    monkeypatch.setenv("BEBSHAX_TRUSTED_PROXY_CIDRS", "10.20.0.0/16")
    assert rate_api._client_key(_peer("198.51.100.10", "203.0.113.40")) == "198.51.100.10"


def test_trusted_chain_selects_first_untrusted_hop_from_right(identity_state, monkeypatch):
    identity_state.settings.rate_limit_trust_forwarded_for = True
    monkeypatch.setenv("BEBSHAX_TRUSTED_PROXY_CIDRS", "10.20.0.0/16")
    request = _peer("10.20.0.2", "203.0.113.99, 198.51.100.7, 10.20.0.1")
    assert rate_api._client_key(request) == "198.51.100.7"


def test_invalid_forwarded_chain_falls_back_to_socket(identity_state, monkeypatch):
    identity_state.settings.rate_limit_trust_forwarded_for = True
    monkeypatch.setenv("BEBSHAX_TRUSTED_PROXY_CIDRS", "10.20.0.0/16")
    assert rate_api._client_key(_peer("10.20.0.2", "attacker, 10.20.0.1")) == "10.20.0.2"