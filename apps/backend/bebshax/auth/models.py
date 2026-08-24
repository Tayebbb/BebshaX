"""SQLAlchemy models for user authentication and accounts."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from bebshax.db.models import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _gen_user_id() -> str:
    return f"usr_{uuid.uuid4().hex[:16]}"


class Users(Base):
    """Registered user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=_gen_user_id
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_provider: Mapped[str] = mapped_column(
        String(32), default="email", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )
