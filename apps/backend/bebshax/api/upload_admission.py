"""Bounded, authenticated admission before FastAPI's multipart spooler."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import Headers

from bebshax.api.errors import APIError

MAX_UPLOAD_FILES = 1
MAX_UPLOAD_FIELDS = 4
MAX_UPLOAD_HEADER_BYTES = 8 * 1024
MAX_UPLOAD_FIELD_BYTES = 32 * 1024
MAX_UPLOAD_BOUNDARY_BYTES = 200
_UPLOAD_PATH = re.compile(r"^/api/(?:studies/[^/]+/)?datasets/upload/?$")


def is_dataset_upload(path: str, root_path: str = "") -> bool:
    if root_path and path.startswith(root_path.rstrip("/") + "/"):
        path = path[len(root_path.rstrip("/")):]
    return _UPLOAD_PATH.fullmatch(path) is not None


def _multipart_limit() -> APIError:
    return APIError(
        413,
        "Multipart upload exceeds the file, field, or part-size limits.",
        error_code="multipart_limits_exceeded",
    )


def _invalid_multipart() -> APIError:
    return APIError(422, "Malformed multipart upload.", error_code="invalid_multipart")


class UploadAdmission:
    """Per-application, fail-fast slots using the existing job-admission cap."""

    def __init__(self) -> None:
        from bebshax.api.jobs import MAX_RUNNING_JOBS_PER_USER

        self.limit = MAX_RUNNING_JOBS_PER_USER
        self.slots = asyncio.BoundedSemaphore(self.limit)
        self.users: dict[str, int] = {}

    @asynccontextmanager
    async def admit(self, request: Request) -> AsyncIterator[None]:
        from bebshax.api.auth import get_current_user
        from bebshax.api.jobs import running_jobs_for_user_async

        if self.slots.locked():
            raise APIError(429, "Upload capacity is busy. Try again later.", error_code="too_many_jobs")
        async with self.slots:
            user = await get_current_user(request, authorization=request.headers.get("authorization"))
            running = await running_jobs_for_user_async(request.app, user.id)
            active = self.users.get(user.id, 0)
            if active + running >= self.limit:
                raise APIError(429, "Your processing capacity is busy. Try again later.", error_code="too_many_jobs")
            self.users[user.id] = active + 1
            try:
                yield
            finally:
                remaining = self.users[user.id] - 1
                if remaining:
                    self.users[user.id] = remaining
                else:
                    del self.users[user.id]


class MultipartGuard:
    """Streaming metadata counter; never retains file contents or creates files."""

    def __init__(self, headers: Headers) -> None:
        content_type = headers.get("content-type", "")
        if len(content_type) > MAX_UPLOAD_HEADER_BYTES:
            raise _multipart_limit()
        media_type, options = parse_options_header(content_type)
        boundary = options.get(b"boundary", b"")
        if media_type != b"multipart/form-data" or not boundary:
            raise _invalid_multipart()
        if len(boundary) > MAX_UPLOAD_BOUNDARY_BYTES:
            raise _multipart_limit()
        self.parts = 0
        self.files = 0
        self.fields = 0
        self.header_bytes = 0
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.disposition = b""
        self.is_file = False
        self.field_bytes = 0
        self.complete = False
        self.parser = MultipartParser(boundary, {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_end": self.on_end,
        })

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts > MAX_UPLOAD_FILES + MAX_UPLOAD_FIELDS:
            raise _multipart_limit()
        self.header_bytes = 0
        self.header_name.clear()
        self.header_value.clear()
        self.disposition = b""
        self.field_bytes = 0
        self.is_file = False

    def _header_fragment(self, target: bytearray, data: bytes, start: int, end: int) -> None:
        self.header_bytes += end - start
        if self.header_bytes > MAX_UPLOAD_HEADER_BYTES:
            raise _multipart_limit()
        target.extend(data[start:end])

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_fragment(self.header_name, data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_fragment(self.header_value, data, start, end)

    def on_header_end(self) -> None:
        if self.header_name.lower() == b"content-disposition":
            self.disposition = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def on_headers_finished(self) -> None:
        disposition, options = parse_options_header(self.disposition)
        if disposition != b"form-data" or b"name" not in options:
            raise _invalid_multipart()
        self.is_file = b"filename" in options
        self.files += int(self.is_file)
        self.fields += int(not self.is_file)
        if self.files > MAX_UPLOAD_FILES or self.fields > MAX_UPLOAD_FIELDS:
            raise _multipart_limit()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self.is_file:
            self.field_bytes += end - start
            if self.field_bytes > MAX_UPLOAD_FIELD_BYTES:
                raise _multipart_limit()

    def on_end(self) -> None:
        self.complete = True

    def feed(self, chunk: bytes, *, final: bool) -> None:
        try:
            self.parser.write(chunk)
            if final:
                self.parser.finalize()
                if not self.complete:
                    raise _invalid_multipart()
        except MultipartParseError:
            raise _invalid_multipart() from None