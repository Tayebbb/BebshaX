"""One error envelope for the whole API, plus the request-context middleware.

Every non-2xx JSON body has the same skeleton::

    {"detail": <human message>, "error_code": <stable snake_case code>, "request_id": <id>}

``request_id`` is the value of the ``X-Request-ID`` response header (echoed
from the client when it is well-formed, generated otherwise), so a user can
quote one id and an operator can find the access-log line and safe stack
locations for it. Exception values, request data and provider error bodies
never reach the public error envelope or this module's logs.
"""

from __future__ import annotations

import logging
import re
import time
import traceback
import uuid
from collections.abc import Mapping
from typing import Any, Optional, get_args

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from pydantic_core import ErrorType
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bebshax.datasets.parser import DatasetParseError
from bebshax.llm.failures import AllCandidatesFailed, ContextWindowExceeded, LLMError
from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("bebshax.access")

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOG_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})

_VALIDATION_TYPES = frozenset(get_args(ErrorType))
_VALIDATION_MESSAGES = {
    "missing": "Field required",
    "extra_forbidden": "Extra inputs are not permitted",
    "int_parsing": "Input should be a valid integer",
    "int_type": "Input should be a valid integer",
    "float_parsing": "Input should be a valid number",
    "float_type": "Input should be a valid number",
    "finite_number": "Input should be a finite number",
    "bool_parsing": "Input should be a valid boolean",
    "bool_type": "Input should be a valid boolean",
    "string_type": "Input should be a valid string",
    "string_too_short": "String is shorter than the allowed minimum",
    "string_too_long": "String exceeds the allowed maximum length",
    "string_pattern_mismatch": "String does not match the required pattern",
    "too_short": "Input contains fewer items than permitted",
    "too_long": "Input contains more items than permitted",
    "list_type": "Input should be a valid list",
    "dict_type": "Input should be a valid dictionary",
    "json_invalid": "Invalid JSON",
    "greater_than": "Input must be greater than the allowed minimum",
    "greater_than_equal": "Input must be at least the allowed minimum",
    "less_than": "Input must be less than the allowed maximum",
    "less_than_equal": "Input must not exceed the allowed maximum",
}

MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
BODY_CAP_EXEMPT_SUFFIXES: tuple[str, ...] = ()
_RECEIVE_CHUNK_BYTES = 64 * 1024

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

_PUBLIC_SERVER_ERRORS = {
    "internal_error": "Internal server error",
    "service_unavailable": "Service unavailable",
    "database_unavailable": "Database unavailable",
    "billing_disabled": "Billing is disabled.",
    "runtime_not_ready": "Application startup validation is incomplete.",
    "ml_persona_unavailable": "Required persona capability is unavailable.",
    "job_store_unavailable": "Durable job storage is unavailable.",
    "job_runtime_closing": "Job runtime is shutting down.",
    "async_job_admission_required": "Processing admission is unavailable.",
}

# 5xx envelopes drop every extra except these fixed operational literals.
_SAFE_SERVER_ERROR_EXTRAS = frozenset({"db"})


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


def _log_path(scope: Scope) -> str:
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) else "[unmatched]"


def _log_method(scope: Scope) -> str:
    method = scope.get("method", "")
    return method if method in _LOG_METHODS else "OTHER"


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
    if exc.status_code >= 500:
        error_code = getattr(exc, "error_code", None)
        if not isinstance(error_code, str) or error_code not in _PUBLIC_SERVER_ERRORS:
            error_code = default_error_code(exc.status_code)
        # Only fixed-literal operational states survive into a 5xx envelope.
        raw_extra = getattr(exc, "extra", None) or {}
        safe_extra = {
            key: value for key, value in raw_extra.items()
            if key in _SAFE_SERVER_ERROR_EXTRAS and isinstance(value, str) and len(value) <= 32
        }
        return _envelope(
            request, exc.status_code, _PUBLIC_SERVER_ERRORS[error_code], error_code,
            safe_extra or None, exc.headers,
        )
    if exc.status_code in (400, 422):
        cause: BaseException | None = exc.__cause__ or exc.__context__
        seen: set[int] = set()
        while cause is not None and id(cause) not in seen and len(seen) < 16:
            if isinstance(cause, DatasetParseError):
                return await dataset_parse_error_handler(request, cause)
            seen.add(id(cause))
            cause = cause.__cause__ or (None if cause.__suppress_context__ else cause.__context__)
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


async def dataset_parse_error_handler(request: Request, exc: DatasetParseError) -> Response:
    return _envelope(request, exc.status_code, exc.detail, exc.error_code)


def _first_validation_message(errors: list[Any]) -> str:
    if not errors:
        return "Request validation failed."
    first = errors[0]
    loc = " → ".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid value"))
    return f"{loc} → {msg}" if loc else msg


def _validation_locations(request: Request) -> set[str]:
    names = {"body", "query", "path", "header", "cookie"}
    pending = [getattr(request.scope.get("route"), "dependant", None)]
    annotations: list[Any] = []
    seen: set[int] = set()
    while pending:
        dependant = pending.pop()
        if dependant is None or id(dependant) in seen:
            continue
        seen.add(id(dependant))
        pending.extend(getattr(dependant, "dependencies", ()))
        for group in ("body_params", "query_params", "path_params", "header_params", "cookie_params"):
            for field in getattr(dependant, group, ()):
                if isinstance(field.alias, str):
                    names.add(field.alias)
                annotations.append(field.field_info.annotation)
    seen.clear()
    while annotations:
        annotation = annotations.pop()
        if id(annotation) in seen:
            continue
        seen.add(id(annotation))
        annotations.extend(get_args(annotation))
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            for name, field in annotation.model_fields.items():
                names.add(name)
                for alias in (field.alias, field.validation_alias):
                    if isinstance(alias, str):
                        names.add(alias)
                annotations.append(field.annotation)
    return names


def _safe_validation_errors(request: Request, exc: RequestValidationError) -> list[dict[str, Any]]:
    allowed_locations = _validation_locations(request)
    errors = []
    for error in exc.errors():
        error_type = error.get("type")
        if type(error_type) is not str or error_type not in _VALIDATION_TYPES:
            error_type = "value_error"
        location = [
            part if (
                (type(part) is str and part in allowed_locations)
                or (type(part) is int and 0 <= part <= 2**31 - 1)
            ) else "[field]"
            for part in error.get("loc", ())
        ]
        errors.append({
            "type": error_type,
            "loc": location,
            "msg": _VALIDATION_MESSAGES.get(error_type, "Invalid value"),
        })
    return errors


def _exception_stack(exc: BaseException) -> str:
    return " > ".join(
        f"{frame.f_code.co_name}:{line_number}"
        for frame, line_number in traceback.walk_tb(exc.__traceback__)
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> Response:
    errors = _safe_validation_errors(request, exc)
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
        _log_method(request.scope),
        _log_path(request.scope),
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
        "database unavailable on %s %s request_id=%s: %s stack=%s",
        _log_method(request.scope),
        _log_path(request.scope),
        request_id_of(request),
        type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
        _exception_stack(exc),
    )
    return _envelope(request, 503, "Database unavailable", "database_unavailable")


async def stale_data_handler(request: Request, exc: StaleDataError) -> Response:
    """An optimistic-revision write lost the race with a concurrent save of the
    same row. Nothing was persisted; the caller reloads and retries."""
    logger.warning(
        "concurrent write conflict on %s %s request_id=%s",
        _log_method(request.scope), _log_path(request.scope), request_id_of(request),
    )
    return _envelope(
        request, 409,
        "This record was changed by another request while saving. Reload and try again; nothing was lost.",
        "write_conflict",
    )


def _attempts_payload(exc: AllCandidatesFailed) -> list[dict[str, Any]]:
    return [
        {
            "provider": attempt.provider,
            "model": attempt.model,
            "failure_kind": str(attempt.failure_kind) if attempt.failure_kind else None,
            "fallback_reason": str(attempt.failure_kind) if attempt.failure_kind else None,
        }
        for attempt in exc.provenance.attempts
    ]


async def all_candidates_failed_handler(request: Request, exc: AllCandidatesFailed) -> Response:
    attempts = _attempts_payload(exc)
    detail = (
        "No AI route could serve this request — all candidates failed."
        if attempts else
        "No AI provider was eligible for this request (remote-processing policy or provider "
        "configuration) — nothing was attempted and nothing was fabricated."
    )
    return _envelope(
        request,
        503,
        detail,
        "all_candidates_failed",
        {
            "llm_request_id": exc.provenance.request_id,
            "attempts": attempts,
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
        "LLM layer error on %s %s request_id=%s: %s stack=%s",
        _log_method(request.scope),
        _log_path(request.scope),
        request_id_of(request),
        type(exc).__name__,
        _exception_stack(exc),
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
        _log_method(request.scope),
        _log_path(request.scope),
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
    logger.error(
        "unhandled exception on %s %s request_id=%s: %s stack=%s",
        _log_method(request.scope), _log_path(request.scope), rid, type(exc).__name__, _exception_stack(exc),
    )
    return _envelope(request, 500, "Internal server error", "internal_error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(DatasetParseError, dataset_parse_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(StaleDataError, stale_data_handler)
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
                _log_method(scope),
                _log_path(scope),
                status_code if status_code is not None else "-",
                duration_ms,
                request_id,
                extra={
                    "method": _log_method(scope),
                    "path": _log_path(scope),
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
        except Exception as exc:
            if response_started:
                raise  # mid-stream: nothing sane to send, let the server close it
            request = Request(scope)
            logger.error(
                "unhandled exception on %s %s request_id=%s: %s stack=%s",
                _log_method(request.scope),
                _log_path(request.scope),
                request_id_of(request),
                type(exc).__name__,
                _exception_stack(exc),
            )
            response = _envelope(request, 500, "Internal server error", "internal_error")
            await response(scope, receive, send)


class BodySizeLimitMiddleware:
    """Count received bytes without prefetching or retaining a request-sized copy.

    Uploads use their existing file-byte ceiling for the entire multipart body,
    with verified admission before the first receive and bounded parser chunks.
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = MAX_REQUEST_BODY_BYTES,
        exempt_suffixes: tuple[str, ...] = BODY_CAP_EXEMPT_SUFFIXES,
    ) -> None:
        from bebshax.api.upload_admission import UploadAdmission
        from bebshax.datasets.security import MAX_DATASET_FILE_SIZE_BYTES

        if exempt_suffixes:
            raise ValueError("Request body-size exemptions are not supported.")
        self.app = app
        self.max_bytes = max_bytes
        self.upload_max_bytes = MAX_DATASET_FILE_SIZE_BYTES
        self.upload_admission = UploadAdmission()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from bebshax.api.upload_admission import MultipartGuard, is_dataset_upload

        upload = scope.get("method") == "POST" and is_dataset_upload(
            scope.get("path", ""), scope.get("root_path", "")
        )
        max_bytes = self.upload_max_bytes if upload else self.max_bytes
        headers = Headers(scope=scope)
        for declared in headers.getlist("content-length"):
            if declared.isascii() and declared.isdigit():
                normalized = declared.lstrip("0") or "0"
                limit = str(max_bytes)
                if len(normalized) > len(limit) or (len(normalized) == len(limit) and normalized > limit):
                    await self._reject(scope, receive, send, max_bytes)
                    return

        guard: MultipartGuard | None = None
        received_bytes = 0
        pending = memoryview(b"")
        pending_more = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, pending, pending_more
            if not pending:
                message = await receive()
                if message["type"] != "http.request":
                    return message
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > max_bytes:
                    raise APIError(
                        413,
                        f"Request body exceeds the {max_bytes // (1024 * 1024)} MiB limit.",
                        error_code="payload_too_large",
                        extra={"max_bytes": max_bytes},
                    )
                pending = memoryview(body)
                pending_more = message.get("more_body", False)
            chunk = bytes(pending[:_RECEIVE_CHUNK_BYTES])
            pending = pending[_RECEIVE_CHUNK_BYTES:]
            more_body = bool(pending) or pending_more
            if guard is not None:
                guard.feed(chunk, final=not more_body)
            return {"type": "http.request", "body": chunk, "more_body": more_body}

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            if upload:
                async with self.upload_admission.admit(Request(scope)):
                    guard = MultipartGuard(headers)
                    await self.app(scope, limited_receive, send_wrapper)
            else:
                await self.app(scope, limited_receive, send_wrapper)
        except StarletteHTTPException as exc:
            if response_started:
                raise
            response = await http_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
        except (OperationalError, InterfaceError) as exc:
            if response_started:
                raise
            response = await database_unavailable_handler(Request(scope), exc)
            await response(scope, receive, send)
        except Exception as exc:
            if response_started:
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, max_bytes: int) -> None:
        response = _envelope(
            Request(scope),
            413,
            f"Request body exceeds the {max_bytes // (1024 * 1024)} MiB limit.",
            "payload_too_large",
            {"max_bytes": max_bytes},
        )
        await response(scope, receive, send)


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
