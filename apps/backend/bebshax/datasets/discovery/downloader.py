"""Bounded downloader for discovered dataset resources.

Catalogue resource URLs are untrusted. Public addresses are validated and
pinned with the original Host/TLS name, credentials and redirects are refused,
and streaming stays within a byte ceiling and a total time budget.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

from bebshax.datasets.security import DatasetSecurityError, Resolver, validate_url_security
from bebshax.utils.explicit_failures import ExplicitFailure

logger = logging.getLogger(__name__)

DATASET_DOWNLOAD_FAILED = "dataset_download_failed"

# Budget table: a discovered resource must stay small enough to profile inside
# a research run on venue Wi-Fi.
MAX_DOWNLOAD_BYTES = 6 * 1024 * 1024
DOWNLOAD_TIMEOUT_S = 20.0
_ALLOWED_SCHEMES = ("http", "https")
_USER_AGENT = "BebshaX/0.1 (dataset discovery; https://github.com/Tayebbb/BebshaX)"


class DatasetDownloadFailed(ExplicitFailure):
    status_code = 502
    error_code = DATASET_DOWNLOAD_FAILED


def looks_downloadable(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        urlsplit(url.strip())
        parsed = httpx.URL(url.strip())
    except (ValueError, httpx.InvalidURL):
        return False
    return parsed.scheme in _ALLOWED_SCHEMES and bool(parsed.host) and not parsed.userinfo


async def fetch_resource_bytes(
    url: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    resolver: Resolver | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Download ``url`` within the budgets. Raises ``DatasetDownloadFailed`` with
    a user-facing reason (security, size, HTTP status, network).

    ``resolver`` and ``http_client`` allow fully offline tests. Connections use
    the same validated-IP and Host/SNI pinning as the shared dataset fetcher.
    """
    if not looks_downloadable(url):
        raise DatasetDownloadFailed(
            "The dataset resource URL must be an http(s) address without credentials."
        )

    original = httpx.URL(url.strip())
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=DOWNLOAD_TIMEOUT_S,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        async with asyncio.timeout(DOWNLOAD_TIMEOUT_S):
            validated_ips = await asyncio.to_thread(
                validate_url_security, str(original), resolver=resolver or socket.getaddrinfo
            )
            hostname = original.raw_host.decode("ascii")
            pinned_url = original.copy_with(host=validated_ips[0])
            headers = {"User-Agent": _USER_AGENT, "Host": original.netloc.decode("ascii")}
            extensions = {"sni_hostname": hostname} if original.scheme == "https" else {}
            async with client.stream(
                "GET",
                pinned_url,
                headers=headers,
                extensions=extensions,
                follow_redirects=False,
                timeout=DOWNLOAD_TIMEOUT_S,
            ) as response:
                if response.status_code != 200:
                    raise DatasetDownloadFailed(
                        f"The source answered HTTP {response.status_code} for the dataset resource.",
                        extra={"url": str(original)},
                    )
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise DatasetDownloadFailed(
                        f"The resource is {int(declared):,} bytes; BebshaX imports at most {max_bytes:,} bytes.",
                        extra={"url": str(original), "size_bytes": int(declared)},
                    )
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise DatasetDownloadFailed(
                            f"The resource exceeded the {max_bytes:,}-byte import ceiling while downloading.",
                            extra={"url": str(original)},
                        )
                    if chunk:
                        chunks.append(chunk)
                meta = {
                    "url": str(original),
                    "content_type": response.headers.get("content-type", ""),
                    "size_bytes": total,
                }
                return b"".join(chunks), meta
    except DatasetDownloadFailed:
        raise
    except DatasetSecurityError as exc:
        raise DatasetDownloadFailed(
            "The dataset resource URL is not a permitted public HTTP(S) address."
        ) from exc
    except TimeoutError as exc:
        raise DatasetDownloadFailed(
            f"The dataset resource download exceeded its {DOWNLOAD_TIMEOUT_S:g}-second time budget.",
            extra={"url": str(original)},
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("dataset resource fetch failed: %s", type(exc).__name__)
        raise DatasetDownloadFailed(
            f"The dataset resource could not be fetched ({type(exc).__name__}).",
            extra={"url": str(original)},
        ) from exc
    finally:
        if owns_client:
            await client.aclose()
