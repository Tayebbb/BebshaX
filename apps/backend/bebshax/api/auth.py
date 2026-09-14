import logging
from asyncio import to_thread
from collections.abc import AsyncIterator
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import AuthSessions, Users, EmailVerificationToken
from bebshax.auth.email import send_password_reset_email, send_verification_email
from bebshax.auth.recovery import request_password_reset, reset_local_password
from bebshax.auth.otp import VERIFY_PURPOSE, consume_otp, issue_otp
from bebshax.auth.security import decode_access_token, hash_password
from bebshax.auth.service import authenticate_user, create_user, get_user_by_email, get_user_by_id
from bebshax.auth.sessions import (
    ACCESS_LIFETIME, SessionCredentials, authenticated_user, aware, find_refresh_session,
    issue_session, lock_user, refresh_user, revoke_family, rotate_session, utc_now,
)
from bebshax.auth.transport import (
    ACCESS_COOKIE, REFRESH_COOKIE, SAFE_METHODS, AuthRoute, access_credential,
    clear_session_cookies, csrf_token, has_auth_cookies, requested_transport,
    require_cookie_binding, require_cookie_csrf, require_cookie_origin, set_session_cookies,
)
from bebshax.api.errors import APIError
from bebshax.api.limiter import clear_account_auth_limit, enforce_auth_limits, limiter
from bebshax.config import get_settings
from bebshax.llm.governance import LLMRequestContext, llm_request_context
from bebshax.tenancy_context import tenant_scope

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"], route_class=AuthRoute)


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def require_valid_unicode(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise ValueError("Invalid text encoding") from None
        return value


class EmailRequest(AuthInput):
    email: str = Field(..., min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class SignUpRequest(EmailRequest):
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

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



class SignInRequest(EmailRequest):
    password: str = Field(..., min_length=1, max_length=128)


from enum import Enum


class AuthProvider(str, Enum):
    EMAIL = "email"
    NEON = "neon"
    GOOGLE = "google"


class UserSyncRequest(AuthInput):
    neon_token: str = Field(..., min_length=1, max_length=8192)
    auth_provider: AuthProvider = AuthProvider.NEON


class VerifiedNeonIdentity(EmailRequest):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    image: str | None = Field(default=None, min_length=1, max_length=512)
    avatar_url: str | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("image", "avatar_url")
    @classmethod
    def validate_avatar_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"https", "http"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or any(ord(character) < 33 for character in value)
            ):
                raise ValueError("Invalid avatar URL")
        return value



class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_verified: bool
    auth_provider: str
    role: str
    created_at: str
    updated_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    expires_in_days: float = 0
    refresh_token: str | None = None
    refresh_expires_in: int = 0
    session_id: str | None = None
    session_expires_at: str | None = None
    csrf_token: str | None = None
    verification_required: bool = False
    user: UserProfileResponse | None = None


def _serialize_user(user: Users) -> UserProfileResponse:
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        auth_provider=user.auth_provider,
        role=user.role or "user",
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
    )


def _verification_required(user: Users) -> bool:
    return not user.is_verified


def _session_response(user: Users, credentials: SessionCredentials, response: Response) -> AuthResponse:
    record = credentials.record
    claims = decode_access_token(credentials.access_token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")
    expires_in = max(0, claims["exp"] - int(datetime.now(timezone.utc).timestamp()))
    cookie_mode = record.transport == "cookie"
    if cookie_mode:
        set_session_cookies(response, credentials)
    return AuthResponse(
        access_token="" if cookie_mode else credentials.access_token,
        refresh_token=None if cookie_mode else credentials.refresh_token,
        expires_in=expires_in, expires_in_days=expires_in / 86400,
        refresh_expires_in=max(0, int((aware(record.refresh_expires_at) - utc_now()).total_seconds())),
        session_id=record.family_id, session_expires_at=record.absolute_expires_at.isoformat(),
        csrf_token=csrf_token(record) if cookie_mode else None,
        user=_serialize_user(user),
    )


async def _issue_auth_response(
    session: AsyncSession, user: Users, request: Request, response: Response,
) -> AuthResponse:
    credentials = await issue_session(session, user, transport=requested_transport(request))
    if credentials is None:
        raise HTTPException(status_code=401, detail="Session has been revoked. Please sign in again.")
    return _session_response(user, credentials, response)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = getattr(request.app.state, "db_sessionmaker", None) or getattr(
        request.app.state, "sessionmaker", None
    )
    if not sessionmaker:
        raise HTTPException(status_code=500, detail="Database not configured")
    async with sessionmaker() as session:
        yield session


async def get_identity_scope() -> AsyncIterator[ExitStack]:
    with ExitStack() as context_stack:
        yield context_stack


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    context_stack: ExitStack = Depends(get_identity_scope),
) -> Users:
    """Dependency to validate JWT and return the current user."""
    token, cookie_mode = access_credential(request, authorization)
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
        user = await authenticated_user(session, payload, transport="cookie" if cookie_mode else "bearer")
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        if cookie_mode:
            record = await session.get(AuthSessions, payload["jti"])
            if record is None:
                raise HTTPException(status_code=401, detail="Invalid session")
            require_cookie_binding(request, record)
            if request.method not in SAFE_METHODS:
                require_cookie_csrf(request, record)
        if _verification_required(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email address not verified.",
            )
        if payload.get("session_version", 0) != user.session_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if isinstance(context_stack, ExitStack):
            context_stack.enter_context(tenant_scope(user.id))
            context_stack.enter_context(llm_request_context(LLMRequestContext(owner_user_id=user.id)))
        return user


async def get_optional_current_user(
    request: Request,
    authorization: str | None = Header(None, alias="Authorization"),
    context_stack: ExitStack = Depends(get_identity_scope),
) -> Users | None:
    """Anonymous means absent credentials, never rejected or unavailable credentials."""
    if authorization is None and not has_auth_cookies(request):
        return None
    return await get_current_user(request, authorization, context_stack)


@auth_router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
# Limits key on socket IP; a demo venue puts every judge behind one NAT address,
# so these are sized per-venue rather than per-person. signin stays at 5/minute.
@limiter.limit("20/hour")
async def signup(
    request: Request,
    payload: SignUpRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    await enforce_auth_limits(request, session, "signup", payload.email)
    pending = AuthResponse(access_token="", verification_required=True)
    try:
        hashed = await to_thread(hash_password, payload.password)
        existing = await get_user_by_email(session, payload.email)
        if existing:
            return pending

        user = await create_user(
            session=session,
            email=payload.email,
            full_name=payload.full_name,
            prehashed_password=hashed,
            auth_provider="email",
        )

        otp_code = await issue_otp(session, user, VERIFY_PURPOSE)
        if otp_code is not None:
            background_tasks.add_task(_deliver_verification, user.email, otp_code)

        return pending
    except IntegrityError:
        await session.rollback()
        return pending
    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.error("Signup failed due to an internal error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed due to an internal error. Please try again.",
        )


class VerifyEmailRequest(EmailRequest):
    token: str = Field(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    purpose: Literal["email-verification"] = "email-verification"


def _invalid_token() -> HTTPException:
    # One reply for unknown email, foreign token, wrong code: never confirm
    # which part was right.
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token.")


@auth_router.post("/verify-email")
@limiter.limit("30/hour")
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Verify a user's email with the OTP issued to that account."""
    await enforce_auth_limits(request, session, "verify", payload.email)
    user = await consume_otp(session, payload.email, VERIFY_PURPOSE, payload.token)
    if not user:
        raise _invalid_token()

    user.is_verified = True
    await session.commit()
    await session.refresh(user)
    auth_response = await _issue_auth_response(session, user, request, response)
    return {"detail": "Email verified successfully.", **auth_response.model_dump()}


class ResendVerificationRequest(AuthInput):
    email: str | None = Field(default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


@auth_router.post("/resend-verification")
@limiter.limit("10/hour")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Optional[ResendVerificationRequest] = None,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[Users] = Depends(get_optional_current_user),
):
    """Resend email verification link (rate-limited)."""
    account = current_user.email if current_user else payload.email if payload else None
    await enforce_auth_limits(request, session, "resend", account)
    # The response is deliberately identical whether or not the address exists
    # and whether or not it is already verified — differing replies let an
    # unauthenticated caller enumerate registered accounts.
    uniform_response = {"detail": "Verification email resent with 6-digit OTP code."}

    target_user = current_user
    if not target_user and payload and payload.email:
        target_user = await get_user_by_email(session, payload.email)

    if not target_user:
        return uniform_response
    otp_code = await issue_otp(session, target_user, VERIFY_PURPOSE)
    if otp_code is not None:
        background_tasks.add_task(_deliver_verification, target_user.email, otp_code)
    return uniform_response


async def _deliver_verification(email: str, code: str) -> None:
    verification_url = f"{get_settings().frontend_base_url.rstrip('/')}/verify-email"
    try:
        await send_verification_email(email, verification_url, otp_code=code)
    except Exception:
        logger.warning("Verification email delivery failed")


class ForgotPasswordRequest(EmailRequest):
    purpose: Literal["forget-password"] = "forget-password"

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class ResetPasswordRequest(ForgotPasswordRequest):
    otp: str = Field(..., pattern=r"^[0-9]{6}$")
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return SignUpRequest.password_must_be_alphanumeric_mix(value)


async def _deliver_password_reset(email: str, code: str) -> None:
    try:
        await send_password_reset_email(email, code)
    except Exception:
        logger.warning("Password recovery email delivery failed")


@auth_router.post("/forgot-password")
@auth_router.post("/request-password-reset")
@limiter.limit("5/hour")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    await enforce_auth_limits(request, session, "forgot", payload.email)
    code = await request_password_reset(session, payload.email)
    if code is not None:
        background_tasks.add_task(_deliver_password_reset, payload.email, code)
    return {"detail": "If the account is eligible, a password reset code has been sent."}


@auth_router.post("/reset-password")
@limiter.limit("10/hour")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    await enforce_auth_limits(request, session, "reset", payload.email)
    if not await reset_local_password(session, payload.email, payload.otp, payload.password):
        raise HTTPException(status_code=400, detail="Invalid or expired password reset code.")
    # The code proved ownership; a lock left by the forgotten password must not outlive it.
    await clear_account_auth_limit(session, "signin", payload.email)
    return {"detail": "Password reset successfully. Please sign in again."}


@auth_router.post("/signin", response_model=AuthResponse)
@limiter.limit("5/minute")
async def signin(
    request: Request,
    payload: SignInRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate with email and password."""
    await enforce_auth_limits(request, session, "signin", payload.email)
    user = await authenticate_user(session, payload.email, payload.password)
    if not user:
        logger.warning("Failed signin attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )
    # H9: the verification link is only meaningful if an unverified account
    # cannot sign in. Gated on environment (Settings.email_verification_enforced)
    # so the local demo keeps working; production and staging enforce.
    if _verification_required(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Email address not verified. Check your inbox for the "
                "verification link, or request a new one at "
                "/api/auth/resend-verification."
            ),
        )

    await clear_account_auth_limit(session, "signin", payload.email)
    return await _issue_auth_response(session, user, request, response)





def _neon_session_url(base_url: str) -> str:
    try:
        parsed = urlsplit(base_url)
        if (
            not 1 <= len(base_url) <= 2048 or parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "\\" in base_url
            or any(ord(character) <= 32 or ord(character) == 127 for character in base_url)
            or parsed.port == 0
        ):
            raise ValueError("Invalid identity service URL")
        return str(httpx.URL(f"{base_url.rstrip('/')}/get-session"))
    except (ValueError, httpx.InvalidURL):
        raise HTTPException(status_code=503, detail="Neon authentication is not configured") from None


async def verify_neon_token(token: str) -> dict:
    """Calls Neon's session-verification endpoint server-side.
    Identity comes only from Neon's verified response — never from client claims."""
    settings = get_settings()
    if not settings.neon_auth_url.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neon authentication is not configured",
        )
    session_url = _neon_session_url(settings.neon_auth_url)
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False) as client:
        try:
            resp = await client.get(
                session_url,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError:
            logger.error("Neon session verification transport failure")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to reach the authentication service. Please try again.",
            )
    if resp.status_code == 429 or resp.status_code >= 500:
        raise HTTPException(status_code=503, detail="Authentication service is unavailable. Please try again.")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Neon session token",
        )
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid identity provider response") from None
    user = data.get("user") if isinstance(data, dict) else None
    if not isinstance(user, dict) or not user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Neon session token",
        )
    return data


@auth_router.post("/sync", response_model=AuthResponse)
@limiter.limit("20/minute")
async def sync_user(
    request: Request,
    payload: UserSyncRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Sync a Neon-authenticated user into the local mirror table.
    Identity comes ONLY from Neon's verified response — never from client input."""
    await enforce_auth_limits(request, session, "sync")
    neon_response = await verify_neon_token(payload.neon_token)
    neon_user = neon_response.get("user") if isinstance(neon_response, dict) and "user" in neon_response else neon_response
    if not isinstance(neon_user, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Neon session payload",
        )

    if neon_user.get("emailVerified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified with identity provider",
        )


    try:
        identity = VerifiedNeonIdentity.model_validate(neon_user)
    except ValidationError:
        raise HTTPException(status_code=401, detail="Invalid identity provider response") from None
    email = identity.email

    await enforce_auth_limits(request, session, "sync", email, include_ip=False)

    full_name = identity.name or identity.full_name or email.split("@", 1)[0]
    avatar_url = identity.image or identity.avatar_url

    user = await get_user_by_email(session, email)
    if not user:
        try:
            user = await create_user(
                session=session, email=email, full_name=full_name,
                auth_provider="neon", avatar_url=avatar_url,
            )
        except IntegrityError:
            await session.rollback()
            user = await get_user_by_email(session, email)
    if user is None:
        raise HTTPException(status_code=503, detail="Identity synchronization is unavailable")
    user = await lock_user(session, user.id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid identity provider response")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    updated = False
    if not user.is_verified and user.hashed_password:
        # Pre-hijack defence: someone may have signed up with THIS address
        # (never proving they own it) and set a password. Linking the verified
        # Neon identity to that row must not leave their password as a
        # second key to the real owner's account.
        user.hashed_password = None
        updated = True
        logger.warning(
            "auth sync: revoked unverified local password for user %s on identity link",
            user.id,
        )
    # Neon proved emailVerified server-side above — persist that fact so
    # backend email/password signins pass the H9 gate from now on.
    if not user.is_verified:
        user.is_verified = True
        updated = True
    if user.auth_provider != "neon":
        user.auth_provider = "neon"
        updated = True
    if full_name and user.full_name != full_name:
        user.full_name = full_name
        updated = True
    if avatar_url and user.avatar_url != avatar_url:
        user.avatar_url = avatar_url
        updated = True
    if updated:
        await session.commit()
        await session.refresh(user)

    return await _issue_auth_response(session, user, request, response)





@auth_router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: Users = Depends(get_current_user)):
    """Retrieve current logged-in user profile."""
    return _serialize_user(current_user)


class RefreshRequest(AuthInput):
    refresh_token: str = Field(..., min_length=76, max_length=76, pattern=r"^[0-9a-f]{32}\.[A-Za-z0-9_-]{43}$")


@auth_router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: Request, response: Response, payload: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(None),
) -> AuthResponse:
    await enforce_auth_limits(request, session, "refresh")
    refresh_value = payload.refresh_token if payload is not None else request.cookies.get(REFRESH_COOKIE)
    if refresh_value is not None:
        record = await find_refresh_session(session, refresh_value)
        cookie_mode = payload is None
        if record is None or record.transport != ("cookie" if cookie_mode else "bearer"):
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        if cookie_mode:
            require_cookie_csrf(request, record)
        await enforce_auth_limits(request, session, "refresh", record.family_id, include_ip=False)
        result = await rotate_session(session, refresh_value)
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        return _session_response(*result, response)
    current_user = await get_current_user(request, authorization)
    await enforce_auth_limits(request, session, "refresh", current_user.id, include_ip=False)
    token = authorization.split(" ", 1)[1].strip() if authorization else ""
    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")
    expires_at = min(claims["exp"], claims["iat"] + int(ACCESS_LIFETIME.total_seconds()))
    expires_in = max(0, expires_at - int(datetime.now(timezone.utc).timestamp()))
    return AuthResponse(
        access_token=token, expires_in=expires_in, expires_in_days=expires_in / 86400,
        user=_serialize_user(current_user),
    )


@auth_router.get("/session")
async def get_browser_session(
    request: Request, session: AsyncSession = Depends(get_session),
) -> dict:
    require_cookie_origin(request)
    await enforce_auth_limits(request, session, "refresh")
    record = await find_refresh_session(session, request.cookies.get(REFRESH_COOKIE, ""))
    if record is None or record.transport != "cookie":
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    require_cookie_binding(request, record)
    user = await refresh_user(session, record)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    await enforce_auth_limits(request, session, "refresh", record.family_id, include_ip=False)
    claims = decode_access_token(request.cookies.get(ACCESS_COOKIE, ""))
    access_user = await authenticated_user(session, claims, transport="cookie") if claims else None
    return {
        "user": _serialize_user(user).model_dump(), "csrf_token": csrf_token(record),
        "session_id": record.family_id,
        "session_expires_at": aware(record.absolute_expires_at).isoformat(),
        "needs_refresh": access_user is None or not claims or claims.get("jti") != record.id,
    }


async def _logout(
    request: Request, response: Response, session: AsyncSession,
    authorization: str | None, payload: RefreshRequest | None, *, all_sessions: bool,
) -> dict[str, str]:
    await enforce_auth_limits(request, session, "logout")
    refresh_value = payload.refresh_token if payload else request.cookies.get(REFRESH_COOKIE) if authorization is None else None
    record = None
    claims = None
    cookie_mode = authorization is None and payload is None and has_auth_cookies(request)
    if refresh_value is not None:
        record = await find_refresh_session(session, refresh_value)
        if record is None or record.transport != ("cookie" if cookie_mode else "bearer"):
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        if cookie_mode:
            require_cookie_csrf(request, record)
        user = await refresh_user(session, record, allow_rotated=not all_sessions)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
    else:
        token, cookie_mode = access_credential(request, authorization)
        claims = decode_access_token(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        user = await authenticated_user(
            session, claims, transport="cookie" if cookie_mode else "bearer",
            allow_rotated=not all_sessions,
        )
        if user is None or _verification_required(user):
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        if claims.get("jti"):
            record = await session.get(AuthSessions, claims["jti"])
            if cookie_mode and record is not None:
                require_cookie_csrf(request, record)
    expected_version = user.session_version
    await enforce_auth_limits(request, session, "logout", user.id, include_ip=False)
    current = await lock_user(session, user.id)
    if current is None or current.session_version != expected_version:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if record is not None:
        await session.refresh(record)
    if refresh_value is not None and record is not None:
        confirmed = await refresh_user(session, record, allow_rotated=not all_sessions)
    elif claims is not None:
        confirmed = await authenticated_user(
            session, claims, transport="cookie" if cookie_mode else "bearer",
            allow_rotated=not all_sessions,
        )
    else:
        confirmed = None
    if confirmed is None or _verification_required(confirmed):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    current.legacy_tokens_revoked_at = utc_now()
    if all_sessions:
        current.session_version += 1
        await session.execute(update(AuthSessions).where(
            AuthSessions.user_id == current.id, AuthSessions.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))
    elif record is not None:
        await revoke_family(session, record.family_id, current.id)
    await session.commit()
    if cookie_mode:
        clear_session_cookies(response)
    return {"detail": "All sessions revoked." if all_sessions else "Signed out successfully."}


@auth_router.post("/logout")
async def logout(
    request: Request, response: Response, payload: RefreshRequest | None = None,
    authorization: str | None = Header(None), session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    return await _logout(request, response, session, authorization, payload, all_sessions=False)


@auth_router.post("/logout-all")
async def logout_all(
    request: Request, response: Response, payload: RefreshRequest | None = None,
    authorization: str | None = Header(None), session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    return await _logout(request, response, session, authorization, payload, all_sessions=True)
