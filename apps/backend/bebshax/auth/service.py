"""Auth service for user registration, login, and retrieval."""

import functools
import secrets
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.auth.security import hash_password, verify_password


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
) -> Users:
    """Create and persist a new user."""
    hashed = hash_password(password) if password else None
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
    user = await get_user_by_email(session, email)
    if not user or not user.hashed_password:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
