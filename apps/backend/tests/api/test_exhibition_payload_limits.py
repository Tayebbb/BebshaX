"""Body-limit regressions using in-process ASGI messages, never a server."""

import json

import pytest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bebshax.api.errors import BodySizeLimitMiddleware


async def _invoke_middleware(
    incoming: list[Message],
    *,
    path: str = "/api/studies",
    headers: list[tuple[bytes, bytes]] | None = None,
    handler: ASGIApp | None = None,
) -> tuple[list[Message], list[str], list[bytes]]:
    pending = iter(incoming)
    sent: list[Message] = []
    app_calls: list[str] = []
    completed_bodies: list[bytes] = []

    async def receive() -> Message:
        return next(pending)

    async def send(message: Message) -> None:
        sent.append(message)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        app_calls.append("handler_entered")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            assert message["type"] == "http.request"
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        completed_bodies.append(bytes(body))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": bytes(body), "more_body": False})

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "root_path": "",
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }
    await BodySizeLimitMiddleware(handler or app, max_bytes=8)(scope, receive, send)
    return sent, app_calls, completed_bodies


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param([], id="missing-length"),
        pytest.param([(b"content-length", b"5")], id="understated-length"),
        pytest.param([(b"content-length", b"0")], id="zero-length"),
        pytest.param([(b"content-length", b"invalid")], id="invalid-length"),
        pytest.param([(b"content-type", b"application/json")], id="chunked-json"),
    ],
)
async def test_chunked_body_over_limit_is_413_before_app(
    headers: list[tuple[bytes, bytes]],
) -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ],
        headers=headers,
    )

    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [413]
    body = json.loads(
        b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    )
    assert body["error_code"] == "payload_too_large"
    assert body["max_bytes"] == 8
    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert dict(response_start["headers"])[b"x-request-id"].decode() == body["request_id"]
    assert app_calls == []
    assert completed_bodies == []


async def test_declared_oversize_body_is_rejected_without_receiving_any_body() -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [], headers=[(b"content-length", b"9")]
    )

    assert sent[0]["status"] == 413
    assert app_calls == []
    assert completed_bodies == []


async def test_overflow_stops_receiving_before_the_request_stream_ends() -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": True},
        ]
    )

    assert sent[0]["status"] == 413
    assert app_calls == []
    assert completed_bodies == []


@pytest.mark.parametrize(
    "chunks",
    [
        pytest.param([b""], id="empty"),
        pytest.param([b"12345"], id="normal-5"),
        pytest.param([b"12345", b"678"], id="exact-8"),
        pytest.param([b"", b"12345", b"", b"678", b""], id="empty-intermediate-frames"),
    ],
)
async def test_body_at_or_below_limit_without_content_length_reaches_app(
    chunks: list[bytes],
) -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
    )

    assert app_calls == ["handler_entered"]
    assert completed_bodies == [b"".join(chunks)]
    assert sent == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"".join(chunks), "more_body": False},
    ]


async def test_disconnect_does_not_complete_the_request() -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    assert sent == []
    assert app_calls == []
    assert completed_bodies == []


async def test_body_replay_preserves_chunks_and_forwards_later_disconnect() -> None:
    incoming: list[Message] = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"678", "more_body": False},
        {"type": "http.disconnect"},
    ]
    observed: list[Message] = []

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        for _ in incoming:
            observed.append(await receive())

    sent, _, _ = await _invoke_middleware(incoming, handler=handler)

    assert observed == incoming
    assert sent == []


async def test_dataset_upload_is_exempt_from_streamed_body_limit() -> None:
    sent, app_calls, completed_bodies = await _invoke_middleware(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ],
        path="/api/datasets/upload",
    )

    assert app_calls == ["handler_entered"]
    assert completed_bodies == [b"1234567890"]
    assert sent == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"1234567890", "more_body": False},
    ]


async def test_upload_exemption_does_not_prefetch_or_check_declared_size() -> None:
    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    sent, _, _ = await _invoke_middleware(
        [],
        path="/api/datasets/upload",
        headers=[(b"content-length", b"9")],
        handler=handler,
    )

    assert sent[0]["status"] == 200


async def test_non_http_scope_passes_through_without_receiving() -> None:
    received_scopes: list[Scope] = []
    scope: Scope = {"type": "websocket", "path": "/api/studies"}

    async def receive() -> Message:
        raise AssertionError("Non-HTTP scopes must not be prefetched")

    async def send(message: Message) -> None:
        raise AssertionError("Non-HTTP scopes must not receive an HTTP response")

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        received_scopes.append(scope)

    await BodySizeLimitMiddleware(handler, max_bytes=8)(scope, receive, send)

    assert received_scopes == [scope]


async def test_midstream_handler_failure_does_not_replace_started_response() -> None:
    sent: list[Message] = []
    scope: Scope = {"type": "http", "path": "/api/studies", "headers": []}

    async def receive() -> Message:
        return {"type": "http.request", "body": b"12345", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def handler(scope: Scope, receive: Receive, send: Send) -> None:
        assert (await receive())["body"] == b"12345"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
        raise RuntimeError("Response stream failed")

    with pytest.raises(RuntimeError, match="Response stream failed"):
        await BodySizeLimitMiddleware(handler, max_bytes=8)(scope, receive, send)

    assert sent == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b"partial", "more_body": True},
    ]