"""Purpose-bound recovery of the local password authority."""

from asyncio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.otp import OTP_LIFETIME as RESET_LIFETIME, OTP_MAX_ATTEMPTS as RESET_MAX_ATTEMPTS
from bebshax.auth.otp import RESET_PURPOSE, consume_otp, issue_otp
from bebshax.auth.security import hash_password
from bebshax.auth.service import get_user_by_email


async def request_password_reset(session: AsyncSession, email: str) -> str | None:
    user = await get_user_by_email(session, email)
    return await issue_otp(session, user, RESET_PURPOSE) if user else None


async def reset_local_password(
    session: AsyncSession, email: str, code: str, password: str,
) -> bool:
    user = await consume_otp(session, email, RESET_PURPOSE, code)
    if user is None:
        return False
    user.hashed_password = await to_thread(hash_password, password)
    user.is_verified = True
    await session.commit()
    return True