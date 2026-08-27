"""Dataset security: SSRF prevention, IP validation, and safe URL streaming fetch."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
import httpx

MAX_DATASET_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
REQUEST_TIMEOUT_SECONDS = 25.0

# Disallowed private and special network ranges
_DISALLOWED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local & Cloud Metadata (AWS/GCP/Azure)
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6 ranges
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # Unique local
    ipaddress.ip_network("fe80::/10"),  # Link local
]

_DISALLOWED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}


class DatasetSecurityError(Exception):
    """Raised when a dataset URL violates security or SSRF constraints."""
    pass


def validate_url_security(url: str) -> None:
    """Inspect URL and resolve IP addresses to block SSRF and internal infrastructure access."""
    if not url or not isinstance(url, str):
        raise DatasetSecurityError("Dataset URL is empty or invalid.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise DatasetSecurityError(f"Unsupported URL protocol: '{parsed.scheme}'. Only HTTP and HTTPS are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise DatasetSecurityError("URL does not specify a valid hostname.")

    hostname_clean = hostname.strip().lower()
    if hostname_clean in _DISALLOWED_HOSTNAMES or hostname_clean.endswith(".local") or hostname_clean.endswith(".internal"):
        raise DatasetSecurityError(f"Access to internal or local hostname '{hostname}' is forbidden.")

    # Resolve hostname to IP addresses
    try:
        addr_infos = socket.getaddrinfo(hostname_clean, None)
    except socket.gaierror as exc:
        raise DatasetSecurityError(f"Unable to resolve hostname '{hostname}': {exc}")

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise DatasetSecurityError(f"Invalid resolved IP address: {ip_str}")

        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise DatasetSecurityError(
                f"URL resolves to restricted/private IP address '{ip_str}'. Access blocked."
            )

        for net in _DISALLOWED_NETWORKS:
            if ip in net:
                raise DatasetSecurityError(
                    f"URL resolves to disallowed IP range '{net}' ({ip_str}). Access blocked."
                )


async def safe_fetch_dataset_bytes(url: str, max_bytes: int = MAX_DATASET_FILE_SIZE_BYTES) -> tuple[bytes, str]:
    """Safely fetch dataset bytes from an external URL with SSRF checks, timeout, and size limits.
    
    Returns:
        (content_bytes, detected_content_type)
    """
    validate_url_security(url)

    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=10.0),
        # Redirects are NOT followed automatically: each hop is re-validated so
        # a public URL cannot 302 into private/metadata address space (SSRF).
        follow_redirects=False,
    ) as client:
        # Pre-flight or GET with stream to prevent memory exhaustion
        try:
            async with client.stream("GET", url, headers={"User-Agent": "BebshaX-Dataset-Fetcher/1.0"}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location", "")
                    raise DatasetSecurityError(
                        f"Redirects are not followed for dataset URLs (got {resp.status_code} → {location[:120]}). "
                        "Provide the final direct URL."
                    )
                if resp.status_code != 200:
                    raise DatasetSecurityError(f"HTTP request returned status {resp.status_code}: {resp.reason_phrase}")

                content_type = resp.headers.get("content-type", "").lower()
                content_length_header = resp.headers.get("content-length")
                if content_length_header:
                    try:
                        content_len = int(content_length_header)
                        if content_len > max_bytes:
                            raise DatasetSecurityError(
                                f"Dataset file size ({content_len / (1024*1024):.1f} MB) exceeds maximum allowed limit of {max_bytes / (1024*1024):.0f} MB."
                            )
                    except ValueError:
                        pass

                chunks: list[bytes] = []
                total_downloaded = 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    total_downloaded += len(chunk)
                    if total_downloaded > max_bytes:
                        raise DatasetSecurityError(
                            f"Dataset file size exceeded maximum allowed limit of {max_bytes / (1024*1024):.0f} MB."
                        )
                    chunks.append(chunk)

                data = b"".join(chunks)
                if not data:
                    raise DatasetSecurityError("Fetched dataset is empty (0 bytes).")
                return data, content_type
        except httpx.TimeoutException:
            raise DatasetSecurityError(f"Dataset download timed out after {REQUEST_TIMEOUT_SECONDS}s.")
        except httpx.TransportError as exc:
            raise DatasetSecurityError(f"Network error fetching dataset: {exc}")
