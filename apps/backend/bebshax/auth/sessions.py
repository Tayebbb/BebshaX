"""Transactional, individually revocable session families and refresh rotation."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import AuthSessions, Users
from bebshax.auth import security

ACCESS_LIFETIME = timedelta(minutes=15)
REFRESH_LIFETIME = timedelta(days=7)
MAX_SESSION_LIFETIME = timedelta(days=30)
REFRESH_PATTERN = re.compile(r"[0-9a-f]{32}\.[A-Za-z0-9_-]{43}\Z")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@dataclass(frozen=True)
class SessionCredentials:
    record: AuthSessions
    access_token: str
    refresh_token: str


async def lock_user(session: AsyncSession, user_id: str) -> Users | None:
    """Serialize credential mutations on PostgreSQL and SQLite, including fresh readers."""
    locked = (await session.execute(
        update(Users).where(Users.id == user_id)
        .values(session_version=Users.session_version).returning(Users.id)
        .execution_options(synchronize_session=False)
    )).scalar_one_or_none()
    if locked is None:
        return None
    return await session.get(Users, user_id, populate_existing=True)


def _new_generation(
    user: Users, *, transport: str, now: datetime,
    absolute_expiry: datetime, family_id: str | None = None,
) -> SessionCredentials:
    session_id = secrets.token_hex(16)
    refresh_token = f"{session_id}.{secrets.token_urlsafe(32)}"
    record = AuthSessions(
        id=session_id, family_id=family_id or session_id, user_id=user.id,
        session_version=user.session_version, transport=transport,
        refresh_token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        created_at=now, access_expires_at=min(now + ACCESS_LIFETIME, absolute_expiry),
        refresh_expires_at=min(now + REFRESH_LIFETIME, absolute_expiry),
        absolute_expires_at=absolute_expiry,
    )
    access_token = security.create_access_token(
        user.id, expires_delta=record.access_expires_at - utc_now(),
        session_version=user.session_version, session_id=record.id,
    )
    return SessionCredentials(record, access_token, refresh_token)


async def issue_session(
    session: AsyncSession, user: Users, *, transport: str = "bearer",
) -> SessionCredentials | None:
    expected_version = user.session_version
    current = await lock_user(session, user.id)
    if current is None or not current.is_active or not current.is_verified or current.session_version != expected_version:
        return None
    now = utc_now()
    lifetime = min(
        timedelta(days=max(1, security.get_settings().jwt_expire_days)), MAX_SESSION_LIFETIME
    )
    credentials = _new_generation(current, transport=transport, now=now, absolute_expiry=now + lifetime)
    session.add(credentials.record)
    await session.commit()
    return credentials


async def authenticated_user(
    session: AsyncSession, claims: dict[str, Any], *, transport: str = "bearer",
    allow_rotated: bool = False,
) -> Users | None:
    user = await session.get(Users, claims["sub"])
    if user is None or not user.is_active or claims.get("session_version", 0) != user.session_version:
        return None
    now = utc_now()
    session_id = claims.get("jti")
    if session_id is None:
        if transport != "bearer":
            return None
        issued_at = datetime.fromtimestamp(claims["iat"], timezone.utc)
        if issued_at + ACCESS_LIFETIME <= now:
            return None
        if user.legacy_tokens_revoked_at is not None:
            return None
        return user
    record = await session.get(AuthSessions, session_id)
    if (
        record is None or record.user_id != user.id or record.session_version != user.session_version
        or record.transport != transport
        or record.revoked_at is not None or (record.rotated_at is not None and not allow_rotated)
        or aware(record.access_expires_at) <= now or aware(record.absolute_expires_at) <= now
    ):
        return None
    return user


async def refresh_user(
    session: AsyncSession, record: AuthSessions, *, allow_rotated: bool = False,
) -> Users | None:
    user = await session.get(Users, record.user_id, populate_existing=True)
    now = utc_now()
    if (
        user is None or not user.is_active or record.session_version != user.session_version
        or record.revoked_at is not None or (record.rotated_at is not None and not allow_rotated)
        or aware(record.refresh_expires_at) <= now or aware(record.absolute_expires_at) <= now
        or not user.is_verified
    ):
        return None
    return user


async def find_refresh_session(session: AsyncSession, refresh_token: str) -> AuthSessions | None:
    if REFRESH_PATTERN.fullmatch(refresh_token) is None:
        return None
    record = await session.get(AuthSessions, refresh_token.split(".", 1)[0], populate_existing=True)
    digest = hashlib.sha256(refresh_token.encode()).hexdigest()
    if record is None or not hmac.compare_digest(record.refresh_token_hash, digest):
        return None
    return record


async def revoke_family(session: AsyncSession, family_id: str, user_id: str) -> None:
    await session.execute(update(AuthSessions).where(
        AuthSessions.family_id == family_id, AuthSessions.user_id == user_id,
        AuthSessions.revoked_at.is_(None),
    ).values(revoked_at=utc_now()))


async def rotate_session(
    session: AsyncSession, refresh_token: str,
) -> tuple[Users, SessionCredentials] | None:
    record = await find_refresh_session(session, refresh_token)
    if record is None:
        return None
    user = await lock_user(session, record.user_id)
    record = await find_refresh_session(session, refresh_token)
    if user is None or record is None:
        return None
    now = utc_now()
    if record.rotated_at is not None:
        await revoke_family(session, record.family_id, record.user_id)
        await session.commit()
        return None
    if (
        not user.is_active or record.session_version != user.session_version
        or record.revoked_at is not None or aware(record.refresh_expires_at) <= now
        or aware(record.absolute_expires_at) <= now
        or not user.is_verified
    ):
        return None
    record.rotated_at = now
    credentials = _new_generation(
        user, transport=record.transport, now=now,
        absolute_expiry=aware(record.absolute_expires_at), family_id=record.family_id,
    )
    session.add(credentials.record)
    await session.commit()
    return user, credentials