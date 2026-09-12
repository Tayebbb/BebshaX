"""Explicit bearer/cookie transport with exact-origin and session-bound CSRF checks."""

from collections.abc import Awaitable, Callable
import hashlib
import hmac

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from bebshax.api.errors import validation_exception_handler
from bebshax.auth.models import AuthSessions
from bebshax.auth import security
from bebshax.auth.sessions import SessionCredentials, aware, utc_now

ACCESS_COOKIE = "__Host-bebshax_access"
REFRESH_COOKIE = "__Secure-bebshax_refresh"
BINDING_COOKIE = "__Host-bebshax_session"
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache", "Vary": "Origin"}
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def has_auth_cookies(request: Request) -> bool:
    return any(name in request.cookies for name in (ACCESS_COOKIE, REFRESH_COOKIE, BINDING_COOKIE))


def requested_transport(request: Request) -> str:
    transport = request.headers.get("x-auth-transport", "cookie" if has_auth_cookies(request) else "bearer")
    if transport not in {"bearer", "cookie"}:
        raise HTTPException(status_code=400, detail="Unsupported authentication transport")
    return transport


def require_cookie_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed = security.get_settings().cors_origins_list
    if (
        request.url.scheme != "https" or not origin or len(origin) > 512
        or origin == "null" or origin not in allowed or len(request.headers.getlist("origin")) != 1
    ):
        raise HTTPException(status_code=403, detail="Untrusted authentication origin")


def csrf_token(record: AuthSessions) -> str:
    return hmac.new(
        security.get_settings().jwt_secret.encode(),
        f"csrf:{record.id}:{record.refresh_token_hash}".encode(), hashlib.sha256,
    ).hexdigest()


def _session_binding(record: AuthSessions, key: str) -> str:
    return hmac.new(
        key.encode(), f"cookie-binding:{record.user_id}:{record.family_id}:{record.session_version}".encode(),
        hashlib.sha256,
    ).hexdigest()


def require_cookie_binding(request: Request, record: AuthSessions) -> None:
    supplied = request.cookies.get(BINDING_COOKIE, "")
    settings = security.get_settings()
    keys = [settings.jwt_secret, settings.jwt_secret_previous]
    if len(supplied) != 64 or not supplied.isascii() or not any(
        key and hmac.compare_digest(supplied, _session_binding(record, key)) for key in keys
    ):
        raise HTTPException(status_code=401, detail="Invalid browser session binding")


def require_cookie_csrf(request: Request, record: AuthSessions) -> None:
    require_cookie_origin(request)
    require_cookie_binding(request, record)
    supplied = request.headers.get("x-csrf-token", "")
    if (
        len(supplied) != 64 or not supplied.isascii()
        or len(request.headers.getlist("x-csrf-token")) != 1
        or not hmac.compare_digest(supplied, csrf_token(record))
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def access_credential(request: Request, authorization: str | None) -> tuple[str, bool]:
    if len(request.headers.getlist("authorization")) > 1:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    if authorization is not None:
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token or len(token) > 4096:
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        return token.strip(), False
    token = request.cookies.get(ACCESS_COOKIE, "")
    if not token or len(token) > 4096:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication credentials")
    if request.method not in SAFE_METHODS:
        require_cookie_origin(request)
    return token, True


def set_session_cookies(response: Response, credentials: SessionCredentials) -> None:
    now = utc_now()
    for name, value, path, expiry in (
        (ACCESS_COOKIE, credentials.access_token, "/", credentials.record.access_expires_at),
        (REFRESH_COOKIE, credentials.refresh_token, "/api/auth", credentials.record.refresh_expires_at),
        (BINDING_COOKIE, _session_binding(credentials.record, security.get_settings().jwt_secret),
         "/", credentials.record.absolute_expires_at),
    ):
        response.set_cookie(
            name, value, path=path, httponly=True, secure=True, samesite="lax",
            max_age=max(0, int((aware(expiry) - now).total_seconds())),
        )


def clear_session_cookies(response: Response) -> None:
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, "/api/auth"), (BINDING_COOKIE, "/")):
        response.delete_cookie(name, path=path, httponly=True, secure=True, samesite="lax")


class AuthRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                if request.method not in SAFE_METHODS and (
                    requested_transport(request) == "cookie" or has_auth_cookies(request)
                ):
                    require_cookie_origin(request)
                response = await handler(request)
            except RequestValidationError as exc:
                response = await validation_exception_handler(request, exc)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), **NO_STORE_HEADERS}
                if exc.status_code == 401:
                    exc.headers["WWW-Authenticate"] = "Bearer"
                raise
            response.headers.update(NO_STORE_HEADERS)
            return response

        return protected