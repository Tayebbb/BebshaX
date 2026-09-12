"""Received-byte limits apply without prefetching or changing SSE output."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel, field_validator
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from starlette.types import Message, Scope

from bebshax.api.errors import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    UnhandledExceptionEnvelopeMiddleware,
    register_exception_handlers,
)


def _scope(path: str, *, headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "headers": headers or [], "server": ("testserver", 80), "client": ("127.0.0.1", 12000),
    }


@pytest.mark.parametrize("path", ["/api/studies", "/api/other/datasets/upload", "/api/datasets/upload/extra", "/api/import"])
@pytest.mark.parametrize("declared", [None, b"0", b"1", b"invalid"])
async def test_all_non_upload_paths_enforce_actual_received_bytes(path: str, declared: bytes | None) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(UnhandledExceptionEnvelopeMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=8)
    app.add_middleware(CORSMiddleware, allow_origins=["https://frontend.test"])
    app.add_middleware(RequestContextMiddleware)
    completed = []

    @app.post(path)
    async def consume(request: Request) -> dict:
        completed.append(await request.body())
        return {"ok": True}

    reads = 0
    sent = []
    chunks = iter([b"12345", b"67890"])

    async def receive() -> Message:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message: Message) -> None:
        sent.append(message)

    headers = [(b"origin", b"https://frontend.test"), (b"x-request-id", b"body-regression")]
    if declared is not None:
        headers.append((b"content-length", declared))
    await app(_scope(path, headers=headers), receive, send)

    assert sent[0]["status"] == 413
    response_headers = dict(sent[0]["headers"])
    body = json.loads(b"".join(message.get("body", b"") for message in sent))
    assert body["error_code"] == "payload_too_large"
    assert body["max_bytes"] == 8
    assert body["request_id"] == response_headers[b"x-request-id"].decode() == "body-regression"
    assert response_headers[b"access-control-allow-origin"] == b"https://frontend.test"
    assert reads == 2
    assert completed == []


@pytest.mark.parametrize("chunks", [[b""], [b"12345", b"678"], [b"", b"12345", b"", b"678", b""]])
async def test_exact_limit_preserves_input_and_forwards_disconnect(chunks: list[bytes]) -> None:
    messages = iter([
        *({"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1} for index, chunk in enumerate(chunks)),
        {"type": "http.disconnect"},
    ])
    observed = []

    async def receive() -> Message:
        return next(messages)

    async def send(message: Message) -> None:
        raise AssertionError("This read-only handler sends no response")

    async def handler(scope, receive, send) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            observed.append(message.get("body", b""))

    await BodySizeLimitMiddleware(handler, max_bytes=8)(_scope("/api/studies"), receive, send)
    assert b"".join(observed) == b"".join(chunks)


async def test_sse_frames_are_not_prefetched_buffered_or_rewritten() -> None:
    sent = []

    async def receive() -> Message:
        raise AssertionError("SSE response must not prefetch an unused request body")

    async def send(message: Message) -> None:
        sent.append(message)

    async def frames():
        assert sent[0]["status"] == 200
        yield b"data: first\n\n"
        assert sent[-1]["body"] == b"data: first\n\n"
        yield b"data: tail-retained\n\n"

    response = StreamingResponse(frames(), media_type="text/event-stream")
    await BodySizeLimitMiddleware(response)(_scope("/api/interviews/stream"), receive, send)

    assert [message.get("body") for message in sent[1:]] == [b"data: first\n\n", b"data: tail-retained\n\n", b""]


async def test_midstream_unexpected_failure_propagates_without_second_response() -> None:
    sent = []

    async def handler(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
        raise RuntimeError("stream-defect")

    async def receive() -> Message:
        raise AssertionError("No request body is needed")

    async def send(message: Message) -> None:
        sent.append(message)

    with pytest.raises(RuntimeError, match="stream-defect"):
        await BodySizeLimitMiddleware(UnhandledExceptionEnvelopeMiddleware(handler))(
            _scope("/api/interviews/stream"), receive, send,
        )

    assert len(sent) == 2
    assert sent[0]["status"] == 200


def test_body_exemptions_cannot_be_reenabled() -> None:
    with pytest.raises(ValueError, match="exempt"):
        BodySizeLimitMiddleware(FastAPI(), exempt_suffixes=("/datasets/upload",))


class BodyLimitPayload(BaseModel):
    password: str


@pytest.mark.parametrize("declared", [None, b"1"])
async def test_chunked_typed_json_is_rejected_before_model_handler(declared) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=8)
    completed = []

    @app.post("/typed-input")
    async def typed_input(payload: BodyLimitPayload):
        completed.append(payload)
        return {"ok": True}

    chunks = iter([b'{"pass', b'word":"private-value"}'])
    messages = []

    async def receive():
        return {"type": "http.request", "body": next(chunks), "more_body": True}

    async def send(message):
        messages.append(message)

    headers = [(b"content-type", b"application/json")]
    if declared is not None:
        headers.append((b"content-length", declared))
    await app(_scope("/typed-input", headers=headers), receive, send)

    assert messages[0]["status"] == 413
    assert completed == []
    assert b"private-value" not in b"".join(message.get("body", b"") for message in messages)


async def test_declared_oversize_is_rejected_before_receiving_body() -> None:
    async def forbidden(*args):
        raise AssertionError("An oversized body must not be received or parsed")

    messages = []

    async def send(message):
        messages.append(message)

    await BodySizeLimitMiddleware(forbidden, max_bytes=8)(
        _scope("/api/auth/signin", headers=[(b"content-length", b"9")]), forbidden, send,
    )

    assert messages[0]["status"] == 413


@pytest.mark.parametrize("declared", [None, b"1"])
@pytest.mark.parametrize("chunked", [False, True])
async def test_typed_json_overflow_is_rejected_before_model_validation(declared, chunked) -> None:
    validated = []

    class Payload(BaseModel):
        value: str

        @field_validator("value")
        @classmethod
        def track_validation(cls, value: str) -> str:
            validated.append(value)
            return value

    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=16)

    async def accept(payload):
        raise AssertionError("Oversized typed bodies must never enter the handler")

    accept.__annotations__["payload"] = Payload
    app.post("/api/typed-input")(accept)
    body = b'{"value":"private-value-beyond-limit"}'
    chunks = [body[:10], body[10:]] if chunked else [body]
    messages = iter([
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ])
    sent = []

    async def receive() -> Message:
        return next(messages)

    async def send(message: Message) -> None:
        sent.append(message)

    headers = [(b"content-type", b"application/json")]
    if declared is not None:
        headers.append((b"content-length", declared))
    await app(_scope("/api/typed-input", headers=headers), receive, send)

    assert sent[0]["status"] == 413
    response = json.loads(b"".join(message.get("body", b"") for message in sent))
    assert response["error_code"] == "payload_too_large"
    assert validated == []