"""Discovery SSRF regressions with literal IPs and an injected mock transport."""

import httpx
import pytest

from bebshax.datasets.discovery.downloader import DatasetDownloadFailed, fetch_resource_bytes

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("127.0.0.1", id="loopback"),
        pytest.param("10.1.2.3", id="private-10"),
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
            await fetch_resource_bytes(f"http://{host}/dataset.csv", http_client=client)

    assert requested_urls == []
    assert rejected.value.error_code == "dataset_download_failed"


async def test_public_resource_redirect_to_loopback_is_rejected_without_following() -> None:
    public_url = "http://93.184.216.34/dataset.csv"
    loopback_url = "http://127.0.0.1/private.csv"
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_url = str(request.url)
        requested_urls.append(requested_url)
        if requested_url == public_url:
            return httpx.Response(302, headers={"location": loopback_url})
        assert requested_url == loopback_url
        return httpx.Response(200, content=b"name,value\nfixture,1\n")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        trust_env=False,
    ) as client:
        with pytest.raises(DatasetDownloadFailed) as rejected:
            await fetch_resource_bytes(public_url, http_client=client)

    assert requested_urls == [public_url]
    assert rejected.value.error_code == "dataset_download_failed"