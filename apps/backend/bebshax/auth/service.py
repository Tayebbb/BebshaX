"""Auth service for user registration, login, and retrieval."""

import functools
import secrets
from asyncio import to_thread
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.auth.security import hash_password, password_hash_usable, verify_password


@functools.lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A throwaway hash of a random secret, computed once per process, so an
    unknown email or a password-less account still costs one full PBKDF2
    verification — otherwise the fast-return timing revealed which emails
    are registered."""
    return hash_password(secrets.token_urlsafe(32))


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[Users]:
    """Retrieve a user by normalized lowercase email."""
    stmt = select(Users).where(Users.email == email.strip().lower())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[Users]:
    """Retrieve a user by ID."""
    stmt = select(Users).where(Users.id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    email: str,
    full_name: str,
    password: Optional[str] = None,
    auth_provider: str = "email",
    avatar_url: Optional[str] = None,
    prehashed_password: str | None = None,
) -> Users:
    """Create and persist a new user."""
    if prehashed_password is not None and (password is not None or not password_hash_usable(prehashed_password)):
        raise ValueError("Invalid prehashed password input")
    hashed = prehashed_password
    if password is not None:
        hashed = await to_thread(hash_password, password)
    user = Users(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        hashed_password=hashed,
        auth_provider=auth_provider,
        avatar_url=avatar_url,
        is_verified=(auth_provider != "email"),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> Optional[Users]:
    """Authenticate a user with email and password.

    Unknown emails and accounts without a usable password (federated or
    revoked) take the same code path length as a wrong password.
    """
    dummy = await to_thread(_dummy_hash)
    user = await get_user_by_email(session, email)
    usable = bool(user and password_hash_usable(user.hashed_password))
    hashed = user.hashed_password if user and usable else dummy
    verified = await to_thread(verify_password, password, hashed or dummy)
    return user if user and user.is_active and usable and verified else None
