"""Public errors and logs must not contain submitted or exception values."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import OperationalError
from starlette.middleware.cors import CORSMiddleware

from bebshax.api.errors import (
    APIError,
    RequestContextMiddleware,
    UnhandledExceptionEnvelopeMiddleware,
    database_unavailable_handler,
    http_exception_handler,
    register_exception_handlers,
    validation_exception_handler,
)

SENSITIVE_SENTINEL = "private-submitted-value-not-for-output"


class RedactionPayload(BaseModel):
    password: int
    attributes: dict[str, int] = {}


class CustomRedactionPayload(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def reject_password(cls, value: str) -> str:
        raise ValueError(value)


@pytest.mark.parametrize("custom_error", [False, True])
def test_validation_errors_use_only_safe_fields_and_messages(custom_error: bool) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.post("/validation")
    async def validate(payload: RedactionPayload) -> dict:
        return payload.model_dump()

    @app.post("/custom-validation")
    async def validate_custom(payload: CustomRedactionPayload) -> dict:
        return payload.model_dump()

    with TestClient(app) as client:
        response = client.post(
            "/custom-validation" if custom_error else "/validation",
            json={"password": SENSITIVE_SENTINEL},
            headers={"X-Request-ID": "redaction-regression"},
        )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "redaction-regression"
    assert response.json()["error_code"] == "validation_error"
    assert SENSITIVE_SENTINEL not in response.text
    assert all(set(error) == {"type", "loc", "msg"} for error in response.json()["detail"])
    assert response.json()["detail"][0]["loc"] == ["body", "password"]


@pytest.mark.asyncio
async def test_untrusted_validation_locations_and_types_are_not_echoed() -> None:
    request = Request({"type": "http", "method": "POST", "path": "/validation", "headers": []})
    error = RequestValidationError([{
        "type": SENSITIVE_SENTINEL,
        "loc": ("body", SENSITIVE_SENTINEL),
        "msg": SENSITIVE_SENTINEL,
        "input": {"password": SENSITIVE_SENTINEL},
        "ctx": {"error": ValueError(SENSITIVE_SENTINEL)},
    }])

    response = await validation_exception_handler(request, error)

    assert response.status_code == 422
    assert SENSITIVE_SENTINEL.encode() not in response.body
    assert set(json.loads(response.body)["detail"][0]) == {"type", "loc", "msg"}


@pytest.mark.asyncio
async def test_database_logs_do_not_format_bound_parameters(caplog: pytest.LogCaptureFixture) -> None:
    request = Request({"type": "http", "method": "POST", "path": "/database", "headers": []})
    error = OperationalError(
        "SELECT private_statement",
        {"password": SENSITIVE_SENTINEL},
        RuntimeError(SENSITIVE_SENTINEL),
    )

    with caplog.at_level(logging.ERROR, logger="bebshax.api.errors"):
        response = await database_unavailable_handler(request, error)

    assert response.status_code == 503
    assert json.loads(response.body)["error_code"] == "database_unavailable"
    assert SENSITIVE_SENTINEL not in caplog.text
    assert "private_statement" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert caplog.records
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
async def test_unexpected_errors_remain_visible_without_exception_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def failing_app(scope, receive, send) -> None:
        raise RuntimeError(SENSITIVE_SENTINEL)

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    messages = []

    async def send(message: dict) -> None:
        messages.append(message)

    with caplog.at_level(logging.ERROR, logger="bebshax.api.errors"):
        await UnhandledExceptionEnvelopeMiddleware(failing_app)(
            {"type": "http", "method": "POST", "path": "/unexpected", "headers": []},
            receive,
            send,
        )

    assert messages[0]["status"] == 500
    assert SENSITIVE_SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "failing_app" in caplog.text
    assert caplog.records
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("status_code", [500, 502, 503])
@pytest.mark.parametrize("structured", [False, True])
def test_plain_server_http_errors_never_echo_arbitrary_details(status_code, structured) -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/wrapped-error")
    async def wrapped_error():
        detail = {"reason": SENSITIVE_SENTINEL} if structured else SENSITIVE_SENTINEL
        raise HTTPException(status_code, detail, headers={"Retry-After": "3"})

    with TestClient(app) as client:
        response = client.get("/wrapped-error")

    assert response.status_code == status_code
    assert response.headers["retry-after"] == "3"
    assert SENSITIVE_SENTINEL not in response.text


def test_authored_service_unavailability_retains_its_safe_code_and_message() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/authored-error")
    async def authored_error():
        raise APIError(503, "Billing is disabled.", error_code="billing_disabled")

    with TestClient(app) as client:
        response = client.get("/authored-error")

    assert response.status_code == 503
    assert response.json()["detail"] == "Billing is disabled."
    assert response.json()["error_code"] == "billing_disabled"


async def test_public_fallback_reason_never_exposes_upstream_detail() -> None:
    from types import SimpleNamespace

    from bebshax.api.errors import all_candidates_failed_handler
    from bebshax.llm.failures import AllCandidatesFailed, FailureKind

    provenance = SimpleNamespace(
        request_id="req_redacted", routing_path=["provider/model"],
        attempts=[SimpleNamespace(
            provider="provider", model="model", failure_kind=FailureKind.SERVER_ERROR,
            fallback_reason=SENSITIVE_SENTINEL,
        )],
    )
    request = Request({"type": "http", "method": "POST", "path": "/completion", "headers": []})
    response = await all_candidates_failed_handler(request, AllCandidatesFailed(provenance))

    assert response.status_code == 503
    assert SENSITIVE_SENTINEL.encode() not in response.body
    attempt = json.loads(response.body)["attempts"][0]
    assert set(attempt) == {"provider", "model", "failure_kind", "fallback_reason"}
    assert attempt["failure_kind"] == "SERVER_ERROR"


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("status_code", [413, 422])
def test_dataset_refusals_keep_coded_status_through_existing_route_wrappers(
    wrapped: bool, status_code: int,
) -> None:
    from bebshax.datasets.parser import DatasetParseError

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=["https://frontend.test"])
    app.add_middleware(RequestContextMiddleware)
    code = "dataset_limits_exceeded" if status_code == 413 else "dataset_unparseable"

    @app.post("/dataset")
    async def parse_dataset() -> None:
        try:
            raise DatasetParseError("Dataset rejected in full.", status_code=status_code, error_code=code)
        except DatasetParseError as error:
            if wrapped:
                raise HTTPException(400, "Uploaded dataset could not be processed.") from error
            raise

    with TestClient(app) as client:
        response = client.post("/dataset", headers={"Origin": "https://frontend.test", "X-Request-ID": "dataset-refusal"})

    assert response.status_code == status_code
    assert response.json()["error_code"] == code
    assert response.json()["detail"] == "Dataset rejected in full."
    assert response.json()["request_id"] == response.headers["X-Request-ID"] == "dataset-refusal"
    assert response.headers["Access-Control-Allow-Origin"] == "https://frontend.test"


def test_dynamic_mapping_keys_are_redacted_from_validation_locations() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/validation")
    async def validate(payload: RedactionPayload) -> dict:
        return payload.model_dump()

    with TestClient(app) as client:
        response = client.post("/validation", json={
            "password": 1, "attributes": {SENSITIVE_SENTINEL: "not-an-integer"},
        })

    assert response.status_code == 422
    assert SENSITIVE_SENTINEL not in response.text
    assert "not-an-integer" not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "attributes", "[field]"]


@pytest.mark.asyncio
async def test_error_and_access_logs_do_not_echo_caller_controlled_url_segments(caplog) -> None:
    async def failing_app(scope, receive, send) -> None:
        raise RuntimeError("Server implementation defect")

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    messages = []

    async def send(message: dict) -> None:
        messages.append(message)

    app = RequestContextMiddleware(UnhandledExceptionEnvelopeMiddleware(failing_app))
    with caplog.at_level(logging.INFO):
        await app({
            "type": "http", "method": "POST", "path": "/private/" + SENSITIVE_SENTINEL,
            "headers": [],
        }, receive, send)

    assert messages[0]["status"] == 500
    assert SENSITIVE_SENTINEL not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "failing_app" in caplog.text


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
@pytest.mark.parametrize("structured", [False, True])
async def test_http_server_errors_do_not_echo_wrapped_exception_details(status_code, structured) -> None:
    request = Request({"type": "http", "method": "POST", "path": "/private", "headers": []})
    detail = {"reason": SENSITIVE_SENTINEL, "input": SENSITIVE_SENTINEL} if structured else SENSITIVE_SENTINEL
    response = await http_exception_handler(request, HTTPException(status_code, detail=detail))

    assert response.status_code == status_code
    assert SENSITIVE_SENTINEL.encode() not in response.body
    assert set(json.loads(response.body)) == {"detail", "error_code", "request_id"}


@pytest.mark.parametrize("status_code,error_code,expected_code", [
    (500, "internal_error", "internal_error"),
    (500, SENSITIVE_SENTINEL, "internal_error"),
    (503, "service_unavailable", "service_unavailable"),
    (503, "billing_disabled", "billing_disabled"),
    (503, "runtime_not_ready", "runtime_not_ready"),
    (503, "ml_persona_unavailable", "ml_persona_unavailable"),
    (503, "job_store_unavailable", "job_store_unavailable"),
    (503, "job_runtime_closing", "job_runtime_closing"),
    (503, "async_job_admission_required", "async_job_admission_required"),
])
async def test_server_error_metadata_uses_only_public_codes(status_code, error_code, expected_code) -> None:
    request = Request({"type": "http", "method": "POST", "path": "/private", "headers": []})
    error = APIError(
        status_code, SENSITIVE_SENTINEL, error_code=error_code,
        extra={"message": SENSITIVE_SENTINEL, "diagnostics": {"password": SENSITIVE_SENTINEL}},
        headers={"Cache-Control": "no-store"},
    )
    response = await http_exception_handler(request, error)

    assert response.status_code == status_code
    assert SENSITIVE_SENTINEL.encode() not in response.body
    assert json.loads(response.body)["error_code"] == expected_code
    assert response.headers["cache-control"] == "no-store"