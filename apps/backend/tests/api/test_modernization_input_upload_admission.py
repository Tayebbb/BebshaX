"""Real FastAPI multipart parsing with counted ASGI receives and spool writes.

These are not no-op route probes: FastAPI parses File/Form parameters before
calling the endpoint dependency, using the installed Starlette spooler.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, File, Form, UploadFile
from sqlalchemy.exc import OperationalError
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Scope

from bebshax.api import errors


@pytest.fixture
def upload_authority(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    with patch("dotenv.load_dotenv", return_value=False), patch(
        "pydantic_settings.sources.DotEnvSettingsSource._read_env_files", return_value={}
    ), patch(
        "pydantic_settings.sources.EnvSettingsSource._load_env_vars",
        return_value={"bebshax_jwt_secret": "test-only-upload-authority-signing-material-12345"},
    ):
        from bebshax.api import auth
        from bebshax.auth import security

    settings = SimpleNamespace(
        jwt_secret="test-only-upload-authority-signing-material-12345",
        jwt_secret_previous=None,
        jwt_expire_days=1,
        jwt_issuer="test-upload-authority",
        jwt_audience="test-upload-client",
        email_verification_enforced=True,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    user = SimpleNamespace(
        id="upload-owner", is_active=True, is_verified=True, session_version=2,
        legacy_tokens_revoked_at=None,
    )
    lookups = []

    class AuthSession:
        async def get(self, model: type, user_id: str) -> SimpleNamespace | None:
            lookups.append(user_id)
            return user if user_id == user.id else None

    @asynccontextmanager
    async def sessionmaker():
        yield AuthSession()

    return SimpleNamespace(
        auth=auth, security=security, user=user, lookups=lookups, sessionmaker=sessionmaker,
        session_class=AuthSession,
        token=security.create_access_token(user.id, session_version=user.session_version),
    )


@pytest.fixture
def spool_probe(monkeypatch: pytest.MonkeyPatch, tmp_path) -> SimpleNamespace:
    import starlette.formparsers as formparsers

    probe = SimpleNamespace(files=[], bytes_written=0)
    original_spool = formparsers.SpooledTemporaryFile

    def counted_spool(*args, **kwargs):
        spool = original_spool(*args, **kwargs)
        probe.files.append(spool)
        original_write = spool.write

        def write(data):
            probe.bytes_written += len(data)
            return original_write(data)

        spool.write = write
        return spool

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", counted_spool)
    monkeypatch.setattr(formparsers.MultiPartParser, "spool_max_size", 64)
    return probe


@pytest.fixture
def multipart_app(upload_authority: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(errors, "MAX_REQUEST_BODY_BYTES", 256)
    from bebshax.datasets import security

    monkeypatch.setattr(security, "MAX_DATASET_FILE_SIZE_BYTES", 2048)
    app = FastAPI()
    from bebshax.jobs.memory import MemoryJobStore

    app.state.db_sessionmaker = upload_authority.sessionmaker
    app.state.job_store = MemoryJobStore()
    app.state.completed = []
    errors.register_exception_handlers(app)
    app.add_middleware(errors.UnhandledExceptionEnvelopeMiddleware)
    app.add_middleware(errors.BodySizeLimitMiddleware, max_bytes=256)
    app.add_middleware(CORSMiddleware, allow_origins=["https://frontend.test"])
    app.add_middleware(errors.RequestContextMiddleware)

    @app.post("/api/datasets/upload")
    @app.post("/api/studies/{study_id}/datasets/upload")
    async def upload(
        file: UploadFile = File(...),
        name: str = Form(...),
        user=Depends(upload_authority.auth.get_current_user),
    ) -> dict:
        content = await file.read()
        app.state.completed.append(content)
        return {"name": name, "content": content.decode(), "user_id": user.id}

    return app


def _multipart(*, file_bytes: bytes = b"a,b\n1,2\n", extra_fields: int = 0, files: int = 1) -> bytes:
    parts = [b'--bounded\r\nContent-Disposition: form-data; name="name"\r\n\r\nDataset\r\n']
    for index in range(extra_fields):
        parts.append(
            f'--bounded\r\nContent-Disposition: form-data; name="field{index}"\r\n\r\nx\r\n'.encode()
        )
    for index in range(files):
        parts.append(
            f'--bounded\r\nContent-Disposition: form-data; name="file"; filename="{index}.csv"\r\n'
            'Content-Type: text/csv\r\n\r\n'.encode() + file_bytes + b"\r\n"
        )
    return b"".join(parts) + b"--bounded--\r\n"


async def _request(
    app: ASGIApp,
    body: bytes,
    *,
    token: str | None = None,
    path: str = "/api/datasets/upload",
    declared: str | None = None,
    before_receive=None,
    chunk_bytes: int = 64,
) -> SimpleNamespace:
    probe = SimpleNamespace(reads=0, received=0, sent=[])
    headers = [
        (b"content-type", b"multipart/form-data; boundary=bounded"),
        (b"origin", b"https://frontend.test"),
        (b"x-request-id", b"upload-admission-test"),
    ]
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    if declared is not None:
        headers.append((b"content-length", declared.encode()))
    else:
        headers.append((b"transfer-encoding", b"chunked"))
    scope: Scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "headers": headers, "server": ("testserver", 80), "client": ("127.0.0.1", 12000),
    }

    async def receive() -> Message:
        if before_receive is not None:
            await before_receive()
        if probe.received >= len(body):
            return {"type": "http.disconnect"}
        start = probe.received
        chunk = body[start:start + chunk_bytes]
        probe.reads += 1
        probe.received += len(chunk)
        return {"type": "http.request", "body": chunk, "more_body": probe.received < len(body)}

    async def send(message: Message) -> None:
        probe.sent.append(message)

    await app(scope, receive, send)
    probe.status = next(message["status"] for message in probe.sent if message["type"] == "http.response.start")
    probe.headers = dict(next(message["headers"] for message in probe.sent if message["type"] == "http.response.start"))
    probe.body = json.loads(b"".join(message.get("body", b"") for message in probe.sent if message["type"] == "http.response.body"))
    return probe


@pytest.mark.parametrize("path", ["/api/datasets/upload", "/api/studies/study-input/datasets/upload", "/api/datasets/upload/"])
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired", "revoked", "inactive", "unverified"])
async def test_rejected_auth_consumes_no_multipart_body(
    multipart_app, upload_authority, spool_probe, path: str, credential: str,
) -> None:
    token = upload_authority.token
    if credential == "missing":
        token = None
    elif credential == "invalid":
        token = "not-a-signed-token"
    elif credential == "expired":
        token = upload_authority.security.create_access_token(
            upload_authority.user.id, timedelta(days=-1), session_version=2,
        )
    elif credential == "revoked":
        upload_authority.user.session_version = 3
    elif credential == "inactive":
        upload_authority.user.is_active = False
    elif credential == "unverified":
        upload_authority.user.is_verified = False

    result = await _request(multipart_app, _multipart(file_bytes=b"x" * 4096), token=token, path=path)

    assert result.status == (403 if credential == "unverified" else 401)
    assert result.received == 0
    assert result.reads == 0
    assert spool_probe.files == []
    assert result.headers[b"access-control-allow-origin"] == b"https://frontend.test"
    assert result.body["request_id"] == result.headers[b"x-request-id"].decode()
    assert multipart_app.state.completed == []


@pytest.mark.parametrize("declared", [None, "0", "8", "invalid"])
async def test_received_upload_limit_stops_spooling_before_complete_body(
    multipart_app, upload_authority, spool_probe, declared: str | None,
) -> None:
    body = _multipart(file_bytes=b"x" * 8192)
    result = await _request(multipart_app, body, token=upload_authority.token, declared=declared)

    assert result.status == 413
    assert result.body["error_code"] == "payload_too_large"
    assert result.body["max_bytes"] == 2048
    assert 0 < result.received <= 2048 + 64 < len(body)
    assert 0 < spool_probe.bytes_written <= 2048
    assert all(spool.closed for spool in spool_probe.files)
    assert multipart_app.state.completed == []


async def test_declared_oversize_upload_never_reads_or_spools(multipart_app, upload_authority, spool_probe) -> None:
    result = await _request(multipart_app, _multipart(), token=upload_authority.token, declared="2049")

    assert result.status == 413
    assert result.reads == 0
    assert spool_probe.files == []


@pytest.mark.parametrize("stage", ["authentication", "durable_count"])
async def test_upload_awaits_authority_and_job_count_before_first_body_receive(
    multipart_app, upload_authority, spool_probe, monkeypatch, stage: str,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    body_started = asyncio.Event()
    original_get = upload_authority.session_class.get

    async def pause() -> None:
        entered.set()
        await release.wait()

    async def held_auth(session, model, user_id):
        await pause()
        return await original_get(session, model, user_id)

    async def held_count(app, owner_id):
        assert owner_id == upload_authority.user.id
        await pause()
        return 0

    async def observe_receive() -> None:
        body_started.set()

    if stage == "authentication":
        monkeypatch.setattr(upload_authority.session_class, "get", held_auth)
    else:
        monkeypatch.setattr("bebshax.api.jobs.running_jobs_for_user_async", held_count)
    content = b"value\ncomplete-private-upload-tail\n"
    pending = asyncio.create_task(_request(
        multipart_app, _multipart(file_bytes=content), token=upload_authority.token,
        before_receive=observe_receive,
    ))
    try:
        async with asyncio.timeout(5):
            await entered.wait()
            assert not body_started.is_set()
            assert spool_probe.files == []
            assert multipart_app.state.completed == []
            release.set()
            result = await pending
        assert result.status == 200
        assert result.body["content"].encode() == content
        assert spool_probe.bytes_written == len(content)
        assert all(spool.closed for spool in spool_probe.files)
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("path", ["/api/datasets/upload", "/api/studies/study-input/datasets/upload"])
async def test_verified_upload_preserves_all_bytes(multipart_app, upload_authority, spool_probe, path: str) -> None:
    content = b"value\n" + b"123456789\n" * 60 + b"tail-must-be-retained\n"
    result = await _request(multipart_app, _multipart(file_bytes=content), token=upload_authority.token, path=path)

    assert result.status == 200
    assert result.body["content"].encode() == content
    assert multipart_app.state.completed == [content]
    assert spool_probe.bytes_written == len(content)
    assert all(spool.closed for spool in spool_probe.files)


@pytest.mark.parametrize(("extra_fields", "files"), [(6, 1), (0, 2)])
async def test_multipart_parts_and_files_are_rejected_before_full_spool(
    multipart_app, upload_authority, spool_probe, extra_fields: int, files: int,
) -> None:
    body = _multipart(file_bytes=b"x" * 512, extra_fields=extra_fields, files=files)
    result = await _request(multipart_app, body, token=upload_authority.token)

    assert result.status == 413
    assert result.body["error_code"] == "multipart_limits_exceeded"
    assert result.received < len(body)
    assert len(spool_probe.files) <= 1
    assert all(spool.closed for spool in spool_probe.files)
    assert multipart_app.state.completed == []


async def test_upload_capacity_is_fail_fast_and_released_after_cancellation(
    multipart_app, upload_authority, spool_probe,
) -> None:
    from bebshax.api.jobs import MAX_RUNNING_JOBS_PER_USER

    entered = 0
    all_entered = asyncio.Event()
    release = asyncio.Event()

    async def block_receive() -> None:
        nonlocal entered
        entered += 1
        if entered == MAX_RUNNING_JOBS_PER_USER:
            all_entered.set()
        await release.wait()

    requests = [
        asyncio.create_task(_request(
            multipart_app, _multipart(), token=upload_authority.token, before_receive=block_receive,
        ))
        for _ in range(MAX_RUNNING_JOBS_PER_USER)
    ]
    try:
        await asyncio.wait_for(all_entered.wait(), timeout=5)
        rejected = await _request(multipart_app, _multipart(), token=upload_authority.token)
        assert rejected.status == 429
        assert rejected.reads == 0
    finally:
        for task in requests:
            task.cancel()
        await asyncio.gather(*requests, return_exceptions=True)

    accepted = await _request(multipart_app, _multipart(), token=upload_authority.token)
    assert accepted.status == 200


@pytest.mark.parametrize("chunk_bytes", [1, 7, 65536])
async def test_multipart_boundaries_split_at_any_frame_preserve_content(
    multipart_app, upload_authority, spool_probe, chunk_bytes: int,
) -> None:
    content = b"value\nall-input-retained\n"
    result = await _request(multipart_app, _multipart(file_bytes=content), token=upload_authority.token, chunk_bytes=chunk_bytes)

    assert result.status == 200
    assert result.body["content"].encode() == content
    assert spool_probe.bytes_written == len(content)
    assert all(spool.closed for spool in spool_probe.files)


@pytest.mark.parametrize("case", ["truncated", "field_size", "header_size"])
async def test_malformed_or_oversize_parts_close_spools_and_reject_in_full(
    multipart_app, upload_authority, spool_probe, monkeypatch, case: str,
) -> None:
    from bebshax.api import upload_admission

    body = _multipart(file_bytes=b"value\nretained\n")
    if case == "truncated":
        body = body[:-14]
    elif case == "field_size":
        monkeypatch.setattr(upload_admission, "MAX_UPLOAD_FIELD_BYTES", 3)
    else:
        monkeypatch.setattr(upload_admission, "MAX_UPLOAD_HEADER_BYTES", 90)
        body = body.replace(b'filename="0.csv"', b'filename="' + b"x" * 100 + b'.csv"')

    result = await _request(multipart_app, body, token=upload_authority.token)

    assert result.status == (422 if case == "truncated" else 413)
    assert result.body["error_code"] == ("invalid_multipart" if case == "truncated" else "multipart_limits_exceeded")
    assert all(spool.closed for spool in spool_probe.files)
    assert multipart_app.state.completed == []


@pytest.mark.parametrize("database_error", [False, True])
async def test_admission_failures_preserve_cors_and_safe_diagnostics(
    multipart_app, upload_authority, spool_probe, monkeypatch, caplog, database_error: bool,
) -> None:
    sentinel = "private-auth-lookup-sentinel"

    async def fail_lookup(session, model, user_id):
        if database_error:
            raise OperationalError("SELECT private_auth", {"input": sentinel}, RuntimeError(sentinel))
        raise RuntimeError(sentinel)

    monkeypatch.setattr(upload_authority.session_class, "get", fail_lookup)
    with caplog.at_level(logging.ERROR, logger="bebshax.api.errors"):
        result = await _request(multipart_app, _multipart(), token=upload_authority.token)

    assert result.status == (503 if database_error else 500)
    assert result.body["error_code"] == ("database_unavailable" if database_error else "internal_error")
    assert result.headers[b"access-control-allow-origin"] == b"https://frontend.test"
    assert result.reads == 0
    assert spool_probe.files == []
    assert sentinel not in caplog.text
    assert "RuntimeError" in caplog.text
    assert caplog.records


async def test_cancellation_closes_a_partially_written_upload(
    multipart_app, upload_authority, spool_probe,
) -> None:
    receive_calls = 0
    paused = asyncio.Event()
    blocked = asyncio.Event()

    async def block_partial() -> None:
        nonlocal receive_calls
        receive_calls += 1
        if receive_calls == 12:
            paused.set()
            await blocked.wait()

    task = asyncio.create_task(_request(
        multipart_app, _multipart(file_bytes=b"x" * 4096), token=upload_authority.token,
        before_receive=block_partial,
    ))
    try:
        await asyncio.wait_for(paused.wait(), timeout=5)
        assert spool_probe.bytes_written > 0
        assert any(not spool.closed for spool in spool_probe.files)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert all(spool.closed for spool in spool_probe.files)
    accepted = await _request(multipart_app, _multipart(), token=upload_authority.token)
    assert accepted.status == 200