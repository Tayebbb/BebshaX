"""Discovery SSRF and download-budget regressions with no real DNS or HTTP."""

import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from bebshax.datasets.discovery import downloader
from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes
from bebshax.datasets.security import Resolver

pytestmark = pytest.mark.asyncio


def _address_info(address: str) -> list[tuple[Any, ...]]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0))]


@pytest.fixture(autouse=True)
def _forbid_real_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_dns(host: str, port: Any, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
        raise AssertionError("Discovery tests must inject an offline resolver")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_dns)


@pytest.fixture
def public_resolver() -> Resolver:
    def resolve(host: str, port: Any) -> list[tuple[Any, ...]]:
        return _address_info("93.184.216.34")

    return resolve


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.chunks_read = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("127.0.0.1", id="loopback"),
        pytest.param("10.1.2.3", id="private-10"),
        pytest.param("169.254.169.254", id="metadata"),
        pytest.param("::1", id="ipv6-loopback"),
        pytest.param("::ffff:127.0.0.1", id="ipv4-mapped-loopback"),
    ],
)
async def test_private_resource_ip_is_rejected_before_transport(host: str) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, content=b"name,value\nfixture,1\n")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        trust_env=False,
    ) as client:
        with pytest.raises(DatasetDownloadFailed) as rejected:
            url_host = f"[{host}]" if ":" in host else host
            await fetch_resource_bytes(
                f"http://{url_host}/dataset.csv",
                http_client=client,
                resolver=lambda hostname, port: _address_info(host),
            )

    assert requested_urls == []
    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
async def test_public_resource_redirect_to_loopback_is_rejected_without_following(
    status_code: int, public_resolver: Resolver,
) -> None:
    public_url = "http://93.184.216.34/dataset.csv"
    loopback_url = "http://127.0.0.1/private.csv"
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_url = str(request.url)
        requested_urls.append(requested_url)
        if requested_url == public_url:
            return httpx.Response(status_code, headers={"location": loopback_url})
        assert requested_url == loopback_url
        return httpx.Response(200, content=b"name,value\nfixture,1\n")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        trust_env=False,
    ) as client:
        with pytest.raises(DatasetDownloadFailed) as rejected:
            await fetch_resource_bytes(public_url, http_client=client, resolver=public_resolver)

    assert requested_urls == [public_url]
    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502
    assert f"HTTP {status_code}" in rejected.value.detail


@pytest.mark.parametrize(
    ("scheme", "address"),
    [
        ("http", "93.184.216.34"),
        ("https", "93.184.216.34"),
        ("https", "2606:2800:220:1:248:1893:25c8:1946"),
    ],
)
async def test_download_pins_dns_answer_and_preserves_host_tls_and_metadata(
    scheme: str, address: str,
) -> None:
    resolutions: list[str] = []
    requests: list[httpx.Request] = []
    original_url = f"{scheme}://catalog.example:8443/data/file.csv?format=csv"

    def resolve(host: str, port: Any) -> list[tuple[Any, ...]]:
        resolutions.append(host)
        return _address_info(address if len(resolutions) == 1 else "127.0.0.1")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True, timeout=None, trust_env=False,
    ) as client:
        body, metadata = await fetch_resource_bytes(
            original_url, http_client=client, resolver=resolve,
        )
        assert not client.is_closed

    assert resolutions == ["catalog.example"]
    assert len(requests) == 1
    request = requests[0]
    assert request.url.host == address
    assert request.url.port == 8443
    assert request.url.path == "/data/file.csv"
    assert request.url.query == b"format=csv"
    assert request.headers["host"] == "catalog.example:8443"
    if scheme == "https":
        assert request.extensions["sni_hostname"] == "catalog.example"
    else:
        assert "sni_hostname" not in request.extensions
    assert request.extensions["timeout"] == {
        kind: downloader.DOWNLOAD_TIMEOUT_S for kind in ("connect", "read", "write", "pool")
    }
    assert body == b"a,b\n1,2\n"
    assert metadata == {"url": original_url, "content_type": "text/csv", "size_bytes": len(body)}


@pytest.mark.parametrize("addresses", [[], ["93.184.216.34", "127.0.0.1"]])
async def test_download_rejects_empty_or_mixed_private_dns_before_transport(
    addresses: list[str],
) -> None:
    requests: list[httpx.Request] = []

    def resolve(host: str, port: Any) -> list[tuple[Any, ...]]:
        return [entry for address in addresses for entry in _address_info(address)]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"a,b\n1,2\n")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        with pytest.raises(DatasetDownloadFailed) as rejected:
            await fetch_resource_bytes(
                "https://catalog.example/data.csv", http_client=client, resolver=resolve,
            )

    assert requests == []
    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502


@pytest.mark.parametrize(
    "url",
    [
        "https://fixture-user:credential-marker@catalog.example/data.csv",
        "http://fixture-user@catalog.example/data.csv",
        "ftp://fixture-user:credential-marker@catalog.example/data.csv",
        "https://[invalid/data.csv",
    ],
)
async def test_invalid_or_credentialed_urls_are_rejected_without_dns_or_disclosure(
    url: str, caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Rejected URLs must not reach the transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        with pytest.raises(DatasetDownloadFailed) as rejected:
            await fetch_resource_bytes(url, http_client=client)

    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502
    assert "credential-marker" not in str(rejected.value)
    assert "fixture-user" not in str(rejected.value)
    assert rejected.value.extra == {}
    assert "credential-marker" not in caplog.text
    assert "fixture-user" not in caplog.text


async def test_streamed_download_over_budget_stops_and_closes_response(
    public_resolver: Resolver,
) -> None:
    stream = _ChunkStream([b"12345", b"67890", b"unread"])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        trust_env=False,
    ) as client:
        with pytest.raises(DatasetDownloadFailed, match="exceeded") as rejected:
            await fetch_resource_bytes(
                "https://catalog.example/data.csv", http_client=client,
                max_bytes=8, resolver=public_resolver,
            )
        assert not client.is_closed

    assert stream.chunks_read == 2
    assert stream.closed
    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502


async def test_declared_download_over_budget_does_not_read_response_body(
    public_resolver: Resolver,
) -> None:
    stream = _ChunkStream([b"12345"])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-length": "9"}, stream=stream)
        ),
        trust_env=False,
    ) as client:
        with pytest.raises(DatasetDownloadFailed, match="at most"):
            await fetch_resource_bytes(
                "https://catalog.example/data.csv", http_client=client,
                max_bytes=8, resolver=public_resolver,
            )

    assert stream.chunks_read == 0
    assert stream.closed


async def test_streamed_download_at_exact_budget_preserves_all_bytes(
    public_resolver: Resolver,
) -> None:
    stream = _ChunkStream([b"12345", b"678"])

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream)),
        trust_env=False,
    ) as client:
        body, metadata = await fetch_resource_bytes(
            "https://catalog.example/data.csv", http_client=client,
            max_bytes=8, resolver=public_resolver,
        )

    assert body == b"12345678"
    assert metadata["size_bytes"] == 8
    assert stream.closed


async def test_total_download_deadline_has_the_existing_failure_shape(
    public_resolver: Resolver, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(downloader, "DOWNLOAD_TIMEOUT_S", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("An exhausted total budget must not reach the transport")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        with pytest.raises(DatasetDownloadFailed, match="time budget") as rejected:
            await fetch_resource_bytes(
                "https://catalog.example/data.csv", http_client=client, resolver=public_resolver,
            )
        assert not client.is_closed

    assert rejected.value.error_code == "dataset_download_failed"
    assert rejected.value.status_code == 502