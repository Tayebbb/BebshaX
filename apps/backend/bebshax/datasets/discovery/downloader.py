"""Bounded downloader for discovered dataset resources.

Resources come from public catalogue APIs (never from user input), but they are
still third-party URLs: only http(s) is followed, redirects are capped, the body
is streamed with a hard byte ceiling and a total time budget, and the result is
handed to the tabular parser exactly as received.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)

DATASET_DOWNLOAD_FAILED = "dataset_download_failed"

# Budget table: a discovered resource must stay small enough to profile inside
# a research run on venue Wi-Fi.
MAX_DOWNLOAD_BYTES = 6 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 20.0
MAX_REDIRECTS = 3
_ALLOWED_SCHEMES = ("http", "https")
_USER_AGENT = "BebshaX/0.1 (dataset discovery; https://github.com/Tayebbb/BebshaX)"


class DatasetDownloadFailed(ExplicitFailure):
    status_code = 502
    error_code = DATASET_DOWNLOAD_FAILED


def looks_downloadable(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in _ALLOWED_SCHEMES and bool(parsed.netloc)


async def fetch_resource_bytes(
    url: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[bytes, dict[str, Any]]:
    """Download ``url`` within the budgets. Raises ``DatasetDownloadFailed`` with
    a user-facing reason (scheme, size, HTTP status, network)."""
    if not looks_downloadable(url):
        raise DatasetDownloadFailed(f"The dataset resource URL is not an http(s) address: {url[:80]!r}.")

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=DOWNLOAD_TIMEOUT_S,
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise DatasetDownloadFailed(
                    f"The source answered HTTP {response.status_code} for the dataset resource.",
                    extra={"url": url},
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise DatasetDownloadFailed(
                    f"The resource is {int(declared):,} bytes; BebshaX imports at most {max_bytes:,} bytes.",
                    extra={"url": url, "size_bytes": int(declared)},
                )
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise DatasetDownloadFailed(
                        f"The resource exceeded the {max_bytes:,}-byte import ceiling while downloading.",
                        extra={"url": url},
                    )
                chunks.append(chunk)
            meta = {
                "url": str(response.url),
                "content_type": response.headers.get("content-type", ""),
                "size_bytes": total,
            }
            return b"".join(chunks), meta
    except DatasetDownloadFailed:
        raise
    except httpx.HTTPError as exc:
        logger.info("dataset resource fetch failed for %s: %s", url, type(exc).__name__)
        raise DatasetDownloadFailed(
            f"The dataset resource could not be fetched ({type(exc).__name__}).", extra={"url": url}
        ) from exc
    finally:
        if owns_client:
            await client.aclose()
