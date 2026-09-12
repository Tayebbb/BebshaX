"""Purpose-bound challenges with keyed digests and transactional single use."""

from datetime import timedelta
import hashlib
import hmac
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth import security
from bebshax.auth.models import EmailVerificationToken, Users
from bebshax.auth.service import get_user_by_email
from bebshax.auth.sessions import aware, lock_user, utc_now

VERIFY_PURPOSE = "email-verification"
RESET_PURPOSE = "forget-password"
OTP_LIFETIME = timedelta(minutes=15)
OTP_MAX_ATTEMPTS = 5


def challenge_digest(record: EmailVerificationToken, code: str) -> str:
    return hmac.new(
        security.get_settings().jwt_secret.encode(),
        f"otp:{record.purpose}:{record.user_id}:{record.id}:{code}".encode(), hashlib.sha256,
    ).hexdigest()


def _eligible(user: Users, purpose: str) -> bool:
    if purpose not in {VERIFY_PURPOSE, RESET_PURPOSE}:
        raise ValueError("Unsupported challenge purpose")
    return bool(
        user.is_active and user.hashed_password
        and (purpose == RESET_PURPOSE or not user.is_verified)
    )


async def issue_otp(session: AsyncSession, user: Users, purpose: str) -> str | None:
    current = await lock_user(session, user.id)
    if current is None or not _eligible(current, purpose):
        return None
    now = utc_now()
    records = (await session.scalars(select(EmailVerificationToken).where(
        EmailVerificationToken.user_id == current.id,
        EmailVerificationToken.purpose == purpose,
        EmailVerificationToken.expires_at > now,
    ).order_by(EmailVerificationToken.created_at.desc(), EmailVerificationToken.id).limit(101))).all()
    if len(records) > 100 or any(record.failed_attempts >= OTP_MAX_ATTEMPTS for record in records):
        return None
    if purpose == RESET_PURPOSE and records and now - aware(records[0].created_at) < timedelta(minutes=1):
        return None
    record = EmailVerificationToken(
        id=str(uuid.uuid4()), user_id=current.id, purpose=purpose,
        session_version=current.session_version, created_at=now,
        expires_at=now + OTP_LIFETIME, failed_attempts=0,
    )
    for attempt in range(16):
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not any(hmac.compare_digest(previous.token, challenge_digest(previous, code)) for previous in records):
            break
    else:
        return None
    record.token = challenge_digest(record, code)
    await session.execute(update(EmailVerificationToken).where(
        EmailVerificationToken.user_id == current.id,
        EmailVerificationToken.purpose == purpose,
        EmailVerificationToken.used_at.is_(None),
    ).values(used_at=now))
    session.add(record)
    await session.commit()
    return code


async def consume_otp(
    session: AsyncSession, email: str, purpose: str, code: str,
) -> Users | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    current = await lock_user(session, user.id)
    if current is None or not _eligible(current, purpose):
        return None
    now = utc_now()
    eligible = (
        EmailVerificationToken.user_id == current.id,
        EmailVerificationToken.purpose == purpose,
        EmailVerificationToken.session_version == current.session_version,
        EmailVerificationToken.used_at.is_(None),
        EmailVerificationToken.expires_at > now,
        EmailVerificationToken.failed_attempts < OTP_MAX_ATTEMPTS,
    )
    record = (await session.scalars(select(EmailVerificationToken).where(*eligible)
        .order_by(EmailVerificationToken.created_at.desc(), EmailVerificationToken.id).limit(1))).one_or_none()
    if record is None:
        return None
    expected = challenge_digest(record, code)
    if not hmac.compare_digest(record.token, expected):
        await session.execute(update(EmailVerificationToken).where(
            *eligible, EmailVerificationToken.id == record.id,
        ).values(failed_attempts=EmailVerificationToken.failed_attempts + 1)
            .execution_options(synchronize_session=False))
        await session.commit()
        return None
    consumed = (await session.execute(update(EmailVerificationToken).where(
        *eligible, EmailVerificationToken.id == record.id, EmailVerificationToken.token == expected,
    ).values(used_at=now).returning(EmailVerificationToken.id)
        .execution_options(synchronize_session=False))).scalar_one_or_none()
    return current if consumed is not None else None