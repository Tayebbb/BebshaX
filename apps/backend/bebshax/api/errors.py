"""One error envelope for the whole API, plus the request-context middleware.

Every non-2xx JSON body has the same skeleton::

    {"detail": <human message>, "error_code": <stable snake_case code>, "request_id": <id>}

``request_id`` is the value of the ``X-Request-ID`` response header (echoed
from the client when it is well-formed, generated otherwise), so a user can
quote one id and an operator can find the single access-log line and any
traceback for it. Internals (provider error bodies, stack traces, ``str(exc)``
of unexpected exceptions) never reach a response body — they go to logs and
provenance records (security rules).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bebshax.llm.failures import AllCandidatesFailed, ContextWindowExceeded, LLMError
from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("bebshax.access")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Requests bigger than this are refused before any handler runs. Dataset uploads
# enforce their own 25 MB ceiling in api/datasets.py and are exempt by path.
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
BODY_CAP_EXEMPT_SUFFIXES = ("/datasets/upload",)

_DEFAULT_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    503: "service_unavailable",
}


def default_error_code(status_code: int) -> str:
    code = _DEFAULT_ERROR_CODES.get(status_code)
    if code:
        return code
    if status_code >= 500:
        return "internal_error"
    return "error"


class APIError(HTTPException):
    """HTTPException with a stable machine-readable ``error_code`` and optional
    extra top-level fields for the envelope (never request-echoing internals)."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        error_code: Optional[str] = None,
        extra: Optional[Mapping[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code or default_error_code(status_code)
        self.extra: dict[str, Any] = dict(extra or {})


def request_id_of(request: Request) -> str:
    """The id stamped by RequestContextMiddleware; generated if the middleware
    did not run (bare app in a unit test) so the field is never null."""
    state = request.scope.get("state") or {}
    rid = state.get("request_id")
    if not rid:
        rid = uuid.uuid4().hex
        request.scope.setdefault("state", {})["request_id"] = rid
    return rid


# Re-exported for API-layer callers; domain engines import it from bebshax.utils.
from bebshax.utils.safe_errors import safe_error_summary  # noqa: E402,F401


def _envelope(
    request: Request,
    status_code: int,
    detail: Any,
    error_code: str,
    extra: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "detail": detail,
        "error_code": error_code,
        "request_id": request_id_of(request),
    }
    if extra:
        for key, value in extra.items():
            body.setdefault(key, value)
    response = JSONResponse(jsonable_encoder(body), status_code=status_code)
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    response.headers[REQUEST_ID_HEADER] = body["request_id"]
    return response


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    if exc.status_code in (204, 304):
        # Starlette parity: these statuses carry no body.
        return Response(status_code=exc.status_code, headers=exc.headers)
    detail = exc.detail
    extra: dict[str, Any] = dict(getattr(exc, "extra", None) or {})
    if not isinstance(detail, str):
        # Structured details (e.g. persona validation violations) stay intact
        # for existing consumers; ``message`` gives clients one string to show.
        if isinstance(detail, Mapping) and isinstance(detail.get("reason"), str):
            extra.setdefault("message", detail["reason"])
        else:
            extra.setdefault("message", "Request failed.")
    error_code = getattr(exc, "error_code", None) or default_error_code(exc.status_code)
    return _envelope(request, exc.status_code, detail, error_code, extra, exc.headers)


def _first_validation_message(errors: list[Any]) -> str:
    if not errors:
        return "Request validation failed."
    first = errors[0]
    loc = " → ".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid value"))
    return f"{loc} → {msg}" if loc else msg


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    errors = jsonable_encoder(exc.errors())
    return _envelope(
        request,
        422,
        errors,
        "validation_error",
        {"message": _first_validation_message(errors)},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> Response:
    # The statement/parameters carry user data — log the class of the DB
    # error and the request id only.
    logger.warning(
        "integrity error on %s %s request_id=%s: %s",
        request.method,
        request.url.path,
        request_id_of(request),
        type(exc.orig).__name__ if exc.orig is not None else "IntegrityError",
    )
    return _envelope(
        request,
        409,
        "The request conflicts with existing data (duplicate or referenced record).",
        "conflict",
    )


async def database_unavailable_handler(request: Request, exc: DBAPIError) -> Response:
    """OperationalError / InterfaceError at request time = the database is
    unreachable (connection refused, dropped, pool exhausted). An honest 503,
    never a 500 traceback; the statement/params never reach the body."""
    logger.error(
        "database unavailable on %s %s request_id=%s: %s",
        request.method,
        request.url.path,
        request_id_of(request),
        type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
        exc_info=exc,
    )
    return _envelope(request, 503, "Database unavailable", "database_unavailable")


def _attempts_payload(exc: AllCandidatesFailed) -> list[dict[str, Any]]:
    return [
        {
            "provider": attempt.provider,
            "model": attempt.model,
            "failure_kind": str(attempt.failure_kind) if attempt.failure_kind else None,
            "fallback_reason": attempt.fallback_reason,
        }
        for attempt in exc.provenance.attempts
    ]


async def all_candidates_failed_handler(request: Request, exc: AllCandidatesFailed) -> Response:
    return _envelope(
        request,
        503,
        "No AI route could serve this request — all candidates failed.",
        "all_candidates_failed",
        {
            "llm_request_id": exc.provenance.request_id,
            "attempts": _attempts_payload(exc),
            "routing_path": list(exc.provenance.routing_path),
        },
    )


async def context_window_exceeded_handler(request: Request, exc: ContextWindowExceeded) -> Response:
    return _envelope(
        request,
        413,
        f"This request needs ~{exc.estimated_tokens} tokens of context; no eligible "
        "model can hold it. Nothing was truncated.",
        "context_window_exceeded",
        {"estimated_tokens": exc.estimated_tokens, "largest_window": exc.largest_window},
    )


async def llm_error_handler(request: Request, exc: LLMError) -> Response:
    logger.warning(
        "LLM layer error on %s %s request_id=%s",
        request.method,
        request.url.path,
        request_id_of(request),
        exc_info=exc,
    )
    return _envelope(
        request,
        502,
        "The AI routing layer could not complete this request.",
        "llm_error",
    )


async def explicit_failure_handler(request: Request, exc: ExplicitFailure) -> Response:
    """Domain refusals (no LLM wired, unusable model output after retry, missing
    precondition) — the honest alternative to templates. Detail text is authored
    by our code, never echoed from a provider."""
    logger.info(
        "explicit failure %s on %s %s request_id=%s",
        exc.error_code,
        request.method,
        request.url.path,
        request_id_of(request),
    )
    return _envelope(request, exc.status_code, exc.detail, exc.error_code, exc.extra)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Sync on purpose: slowapi's middleware path falls back to its own default
    handler for coroutine handlers, and that default has no envelope fields."""
    message = f"Rate limit exceeded: {exc.detail}"
    response = _envelope(request, 429, message, "rate_limited", {"error": message})
    view_limit = getattr(request.state, "view_rate_limit", None)
    limiter = getattr(request.app.state, "limiter", None)
    if limiter is not None and view_limit is not None:
        response = limiter._inject_headers(response, view_limit)
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    rid = request_id_of(request)
    # ServerErrorMiddleware sends this response itself, bypassing the
    # middleware's send wrapper — so the header is set here too.
    logger.exception(
        "unhandled exception on %s %s request_id=%s", request.method, request.url.path, rid
    )
    return _envelope(request, 500, "Internal server error", "internal_error")


def register_exception_handlers(app) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, database_unavailable_handler)
    app.add_exception_handler(InterfaceError, database_unavailable_handler)
    # Most specific LLM failures first; LLMError is the base-class fallback.
    app.add_exception_handler(AllCandidatesFailed, all_candidates_failed_handler)
    app.add_exception_handler(ContextWindowExceeded, context_window_exceeded_handler)
    app.add_exception_handler(LLMError, llm_error_handler)
    app.add_exception_handler(ExplicitFailure, explicit_failure_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


# ---------------------------------------------------------------------------
# Middleware (pure ASGI so 4xx/5xx from every layer pass through it)
# ---------------------------------------------------------------------------

class RequestContextMiddleware:
    """Stamps ``request.state.request_id``, echoes/sets ``X-Request-ID`` on the
    response, and emits exactly one access-log line per request. Never logs
    headers, bodies, query strings, or tokens."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        started = time.perf_counter()
        status_code: Optional[int] = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = status_code or 500
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            access_logger.info(
                "method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_code if status_code is not None else "-",
                duration_ms,
                request_id,
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code,
                    "duration_ms": round(duration_ms, 1),
                    "request_id": request_id,
                },
            )


class UnhandledExceptionEnvelopeMiddleware:
    """Turns an unexpected exception into the 500 envelope *inside* the CORS and
    security-header layers.

    Starlette's ``Exception`` handler runs in ``ServerErrorMiddleware`` — outside
    every ``add_middleware`` layer — so its response carries no CORS headers and a
    cross-origin SPA sees an opaque network error instead of a ``request_id``.
    Installing this catcher inner to CORS fixes that; the Starlette handler stays
    as the backstop for anything raised by the middlewares themselves.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if response_started:
                raise  # mid-stream: nothing sane to send, let the server close it
            request = Request(scope)
            logger.exception(
                "unhandled exception on %s %s request_id=%s",
                request.method,
                request.url.path,
                request_id_of(request),
            )
            response = _envelope(request, 500, "Internal server error", "internal_error")
            await response(scope, receive, send)


class BodySizeLimitMiddleware:
    """Refuses declared bodies above ``max_bytes`` with the 413 envelope before
    any handler runs. Only ``Content-Length`` is inspected: streaming/chunked
    bodies are bounded by the routes that accept them."""

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_REQUEST_BODY_BYTES,
        exempt_suffixes: tuple[str, ...] = BODY_CAP_EXEMPT_SUFFIXES,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exempt_suffixes = exempt_suffixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            declared = Headers(scope=scope).get("content-length", "")
            if (
                declared.isdigit()
                and int(declared) > self.max_bytes
                and not path.endswith(self.exempt_suffixes)
            ):
                request = Request(scope)
                response = _envelope(
                    request,
                    413,
                    f"Request body exceeds the {self.max_bytes // (1024 * 1024)} MiB limit.",
                    "payload_too_large",
                    {"max_bytes": self.max_bytes},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


__all__ = [
    "APIError",
    "BODY_CAP_EXEMPT_SUFFIXES",
    "BodySizeLimitMiddleware",
    "MAX_REQUEST_BODY_BYTES",
    "REQUEST_ID_HEADER",
    "RequestContextMiddleware",
    "UnhandledExceptionEnvelopeMiddleware",
    "default_error_code",
    "register_exception_handlers",
    "request_id_of",
    "safe_error_summary",
]
