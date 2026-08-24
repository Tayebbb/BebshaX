"""Auth service for user registration, login, and retrieval."""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.auth.security import hash_password, verify_password


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
    """Authenticate a user with email and password."""
    user = await get_user_by_email(session, email)
    if not user or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
