"""Shared endpoint limiter plus transactional account/IP authentication budgets."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import math
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from bebshax.api.errors import APIError
from bebshax.auth.models import AuthRateLimits
from bebshax.config import get_settings


def _hop_ip(hop: str) -> str | None:
    """Parse an XFF hop into a validated IP, tolerating proxy port suffixes.

    Handles "1.2.3.4", "1.2.3.4:51423" (IIS/ARR style), "2001:db8::1", and
    "[2001:db8::1]:443". Returns None for anything that isn't an IP.
    """
    candidate = hop.strip()
    if "%" in candidate:
        return None
    if candidate.startswith("[") and "]" in candidate:  # bracketed IPv6[:port]
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # IPv4:port (bare IPv6 has ≥2 colons)
        candidate = candidate.split(":", 1)[0]
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return str(parsed)


def _trusted_proxy_networks() -> tuple:
    configured = os.environ.get("BEBSHAX_TRUSTED_PROXY_CIDRS", "")
    if not configured or len(configured) > 2048:
        return ()
    entries = configured.split(",")
    if len(entries) > 32:
        return ()
    try:
        return tuple(ipaddress.ip_network(entry.strip(), strict=True) for entry in entries)
    except ValueError:
        return ()


def _client_key(request: Request) -> str:
    settings = get_settings()
    remote = get_remote_address(request)
    peer = _hop_ip(remote)
    networks = _trusted_proxy_networks() if settings.rate_limit_trust_forwarded_for else ()
    if peer is None or not networks:
        return peer or remote
    if not any(ipaddress.ip_address(peer) in network for network in networks):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded or len(forwarded) > 2048:
        return peer
    hops = forwarded.split(",")
    if len(hops) > 32:
        return peer
    for hop in reversed(hops):
        address = _hop_ip(hop)
        if address is None:
            return peer
        if not any(ipaddress.ip_address(address) in network for network in networks):
            return address
    return peer


@dataclass(frozen=True)
class AuthRatePolicy:
    ip_limit: int
    ip_window: int
    account_limit: int
    account_window: int


AUTH_RATE_POLICIES = {
    "signup": AuthRatePolicy(20, 3600, 5, 3600),
    "signin": AuthRatePolicy(30, 60, 5, 900),
    "verify": AuthRatePolicy(30, 3600, 5, 900),
    "resend": AuthRatePolicy(10, 3600, 5, 900),
    "forgot": AuthRatePolicy(10, 3600, 5, 3600),
    "reset": AuthRatePolicy(10, 3600, 10, 900),
    "sync": AuthRatePolicy(20, 60, 20, 60),
    "refresh": AuthRatePolicy(60, 60, 30, 60),
    "logout": AuthRatePolicy(60, 60, 30, 60),
}


async def enforce_auth_limits(
    request: Request, session: AsyncSession, action: str,
    account: str | None = None, *, include_ip: bool = True,
) -> None:
    policy = AUTH_RATE_POLICIES[action]
    identities = []
    if include_ip:
        identities.append(("ip", _client_key(request), policy.ip_limit, policy.ip_window))
    if account is not None:
        identities.append(("account", account.strip().lower(), policy.account_limit, policy.account_window))
    now = datetime.now(timezone.utc)
    retry_after = 0
    dialect = session.get_bind().dialect.name
    insert = {"postgresql": postgres_insert, "sqlite": sqlite_insert}.get(dialect)
    if insert is None:
        raise APIError(503, "Authentication storage is unavailable.")
    try:
        for kind, identity, limit, window in identities:
            key = hmac.new(
                get_settings().jwt_secret.encode(), f"auth:{action}:{kind}:{identity}".encode(), hashlib.sha256,
            ).hexdigest()
            expiry = now + timedelta(seconds=window)
            elapsed = AuthRateLimits.expires_at <= now
            statement = insert(AuthRateLimits).values(key=key, attempts=1, expires_at=expiry)
            statement = statement.on_conflict_do_update(
                index_elements=[AuthRateLimits.key],
                set_={
                    "attempts": case(
                        (elapsed, 1), (AuthRateLimits.attempts >= limit + 1, limit + 1),
                        else_=AuthRateLimits.attempts + 1,
                    ),
                    "expires_at": case((elapsed, expiry), else_=AuthRateLimits.expires_at),
                },
            ).returning(AuthRateLimits.attempts, AuthRateLimits.expires_at)
            attempts, expires_at = (await session.execute(statement)).one()
            if attempts > limit:
                deadline = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
                retry_after = max(retry_after, max(1, math.ceil((deadline - now).total_seconds())))
                break
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise APIError(503, "Authentication storage is unavailable.") from None
    if retry_after:
        raise APIError(
            429, "Too many authentication attempts. Try again later.",
            error_code="too_many_attempts", headers={"Retry-After": str(retry_after)},
        )


def _build_limiter() -> Limiter:
    storage_uri = get_settings().rate_limit_storage_uri
    if storage_uri:
        return Limiter(key_func=_client_key, storage_uri=storage_uri)
    return Limiter(key_func=_client_key)


limiter = _build_limiter()
