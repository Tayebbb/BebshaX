import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.db.models import Base
from bebshax.auth.models import Users, EmailVerificationToken


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_email_verification_token_table_exists(db_session):
    """Stage 1: EmailVerificationToken model attributes and persistence."""
    assert hasattr(EmailVerificationToken, "token")
    assert hasattr(EmailVerificationToken, "expires_at")
    assert hasattr(EmailVerificationToken, "used_at")

    user = Users(
        id="usr_test_verify_01",
        email="verifytest@example.com",
        full_name="Verify Test",
        auth_provider="email",
        is_verified=False,
    )
    db_session.add(user)
    await db_session.commit()

    token_record = EmailVerificationToken(
        id="tok_12345",
        user_id=user.id,
        token="random_token_val_12345",
        expires_at=EmailVerificationToken.generate_expiry(24),
    )
    db_session.add(token_record)
    await db_session.commit()

    result = await db_session.execute(
        select(EmailVerificationToken).where(EmailVerificationToken.token == "random_token_val_12345")
    )
    loaded = result.scalar_one_or_none()
    assert loaded is not None
    assert loaded.user_id == "usr_test_verify_01"
    assert loaded.used_at is None
    assert loaded.expires_at > datetime.now(timezone.utc)
