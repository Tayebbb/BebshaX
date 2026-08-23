"""FastAPI authentication routes: signup, signin, current user profile, Google auth."""

from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token, decode_access_token
from bebshax.auth.service import authenticate_user, create_user, get_user_by_email, get_user_by_id

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)


class SignInRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    auth_provider: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_days: int = 7
    user: UserProfileResponse


def _serialize_user(user: Users) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        auth_provider=user.auth_provider,
        created_at=user.created_at.isoformat(),
    )


async def get_session(request: Request) -> AsyncSession:
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None) or getattr(
        request.app.state, "sessionmaker", None
    )
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        yield session


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Users:
    """Dependency to validate JWT and return the current user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload["sub"]
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None) or getattr(
        request.app.state, "sessionmaker", None
    )
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        user = await get_user_by_id(session, user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user


@auth_router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignUpRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user account."""
    existing = await get_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    user = await create_user(
        session=session,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        auth_provider="email",
    )

    token = create_access_token(
        data={"sub": user.id, "email": user.email, "name": user.full_name}
    )
    return AuthResponse(
        access_token=token,
        user=_serialize_user(user),
    )


@auth_router.post("/signin", response_model=AuthResponse)
async def signin(
    payload: SignInRequest,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate with email and password."""
    user = await authenticate_user(session, payload.email, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    token = create_access_token(
        data={"sub": user.id, "email": user.email, "name": user.full_name}
    )
    return AuthResponse(
        access_token=token,
        user=_serialize_user(user),
    )


@auth_router.post("/google", response_model=AuthResponse)
async def google_auth(
    payload: GoogleAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate or register seamlessly with Google."""
    email = payload.email or "google.user@example.com"
    full_name = payload.name or "Google User"

    user = await get_user_by_email(session, email)
    if not user:
        user = await create_user(
            session=session,
            email=email,
            full_name=full_name,
            auth_provider="google",
            avatar_url=payload.avatar_url,
        )

    token = create_access_token(
        data={"sub": user.id, "email": user.email, "name": user.full_name}
    )
    return AuthResponse(
        access_token=token,
        user=_serialize_user(user),
    )


@auth_router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: Users = Depends(get_current_user)):
    """Retrieve current logged-in user profile."""
    return _serialize_user(current_user)
