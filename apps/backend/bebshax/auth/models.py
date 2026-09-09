"""SQLAlchemy models for user authentication and accounts."""

from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, event, inspect, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

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
    session_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    auth_provider: Mapped[str] = mapped_column(
        String(32), default="email", nullable=False
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    subscription_plan: Mapped[str] = mapped_column(
        String(32), default="free", nullable=False
    )
    subscription_status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


@event.listens_for(Users, "before_update")
def _revoke_sessions_on_credential_change(
    _mapper: Mapper[Users], connection: Connection, user: Users,
) -> None:
    """Revoke ORM-managed credential changes atomically, including stale snapshots."""
    state = inspect(user)
    if not any(
        state.attrs[field].history.has_changes()
        for field in ("hashed_password", "auth_provider", "is_verified")
    ):
        return
    user.session_version = connection.execute(
        update(Users)
        .where(Users.id == user.id)
        .values(session_version=Users.session_version + 1)
        .returning(Users.session_version)
    ).scalar_one()



from datetime import timedelta
from sqlalchemy import ForeignKey


class EmailVerificationToken(Base):
    """Email verification token for confirming user email addresses."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @staticmethod
    def generate_expiry(hours: int = 24) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=hours)

