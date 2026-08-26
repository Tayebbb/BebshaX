from datetime import timedelta
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token, decode_access_token
from bebshax.auth.service import authenticate_user, create_user, get_user_by_email, get_user_by_id
from bebshax.config import get_settings

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


from pydantic import BaseModel, Field, field_validator


class SignUpRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_be_alphanumeric_mix(cls, v: str) -> str:
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError(
                "Password must contain at least one letter and one number "
                "(matches the requirement shown at signup)."
            )
        return v



class SignInRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class UserSyncRequest(BaseModel):
    neon_token: str = Field(..., min_length=1)
    auth_provider: str = "neon"


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    auth_provider: str
    created_at: str
    updated_at: str


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
        updated_at=user.updated_at.isoformat(),
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


async def get_optional_current_user(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
) -> Users | None:
    """Extract and validate current user if Bearer token is provided, otherwise return None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None

    user_id = payload["sub"]
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None) or getattr(
        request.app.state, "sessionmaker", None
    )
    if not sessionmaker:
        return None
    try:
        async with sessionmaker() as session:
            user = await get_user_by_id(session, user_id)
            if user and user.is_active:
                return user
    except Exception:
        pass
    return None


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

    token = create_access_token(user_id=user.id)
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

    token = create_access_token(user_id=user.id)
    return AuthResponse(
        access_token=token,
        user=_serialize_user(user),
    )



async def verify_neon_token(token: str) -> dict:
    """Calls Neon's session-verification endpoint server-side.
    Identity comes only from Neon's verified response — never from client claims."""
    settings = get_settings()
    base_url = settings.neon_auth_url.rstrip("/")
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                f"{base_url}/get-session",
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Unable to reach Neon authentication service: {exc}",
            )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Neon session token",
        )
    data = resp.json()
    user = data.get("user") if isinstance(data, dict) else None
    if not user or not user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Neon session token",
        )
    return data


@auth_router.post("/sync", response_model=AuthResponse)
async def sync_user(
    payload: UserSyncRequest,
    session: AsyncSession = Depends(get_session),
):
    """Sync a Neon-authenticated user into the local mirror table.
    Identity comes ONLY from Neon's verified response — never from client input."""
    neon_response = await verify_neon_token(payload.neon_token)
    neon_user = neon_response.get("user") if isinstance(neon_response, dict) and "user" in neon_response else neon_response
    if not isinstance(neon_user, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Neon session payload",
        )

    if not neon_user.get("emailVerified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified with identity provider",
        )


    email = (neon_user.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified Neon session returned no email address",
        )

    full_name = neon_user.get("name") or neon_user.get("full_name") or email.split("@")[0]
    avatar_url = neon_user.get("image") or neon_user.get("avatar_url")

    user = await get_user_by_email(session, email)
    if not user:
        user = await create_user(
            session=session,
            email=email,
            full_name=full_name,
            auth_provider=payload.auth_provider,
            avatar_url=avatar_url,
        )
    else:
        updated = False
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            updated = True
        if updated:
            await session.commit()
            await session.refresh(user)

    token = create_access_token(user_id=user.id)
    return AuthResponse(
        access_token=token,
        user=_serialize_user(user),
    )





@auth_router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: Users = Depends(get_current_user)):
    """Retrieve current logged-in user profile."""
    return _serialize_user(current_user)


@auth_router.post("/refresh", response_model=AuthResponse)
async def refresh_token(current_user: Users = Depends(get_current_user)):
    """Refresh a valid access token and return a new persistent JWT session."""
    token = create_access_token(user_id=current_user.id)
    return AuthResponse(
        access_token=token,
        user=_serialize_user(current_user),
    )


@auth_router.get("/users", response_model=list[UserProfileResponse])
async def list_users(
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[UserProfileResponse]:
    """Return all registered user accounts. Requires a valid login token."""
    result = await session.execute(select(Users).order_by(Users.created_at.desc()))
    users = list(result.scalars().all())
    return [_serialize_user(u) for u in users]
