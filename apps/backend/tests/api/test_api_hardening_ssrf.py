"""Dataset fetch SSRF: the address that was validated is the address connected to.

DNS rebinding = answer the validation lookup with a public IP, then answer the
HTTP client's own lookup with 127.0.0.1 / 169.254.169.254. The fetch now pins
the validated IP into the URL (Host + SNI keep the real hostname), so there is
no second lookup for an attacker to poison.
"""

import socket

import httpx
import pytest

from bebshax.datasets.security import (
    DatasetSecurityError,
    safe_fetch_dataset_bytes,
    validate_url_security,
)

_PUBLIC = "93.184.216.34"
_LOOPBACK = "127.0.0.1"
_METADATA = "169.254.169.254"


def _addrinfo(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]


class _RebindingResolver:
    """First answer public, every later answer attacker-controlled."""

    def __init__(self, later: str):
        self.calls = 0
        self._later = later

    def __call__(self, host, port):
        self.calls += 1
        return _addrinfo(_PUBLIC if self.calls == 1 else self._later)


def _capture_transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"a,b\n1,2\n", headers={"content-type": "text/csv"})

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("rebound_to", [_LOOPBACK, _METADATA])
async def test_fetch_connects_to_the_validated_ip_never_the_rebound_answer(rebound_to: str):
    resolver = _RebindingResolver(later=rebound_to)
    seen: list[httpx.Request] = []

    data, ctype = await safe_fetch_dataset_bytes(
        "https://Example.com:8443/data/file.csv?x=1",
        resolver=resolver,
        transport=_capture_transport(seen),
    )

    assert data == b"a,b\n1,2\n" and ctype == "text/csv"
    assert resolver.calls == 1, "exactly one resolution — nothing left to rebind"
    req = seen[0]
    assert req.url.host == _PUBLIC and req.url.port == 8443
    assert req.url.path == "/data/file.csv" and req.url.query == b"x=1"
    assert req.headers["host"] == "example.com"
    assert req.extensions["sni_hostname"] == "example.com"
    assert rebound_to not in str(req.url)


async def test_plain_http_pins_ip_without_sni():
    seen: list[httpx.Request] = []
    await safe_fetch_dataset_bytes(
        "http://example.com/f.csv", resolver=lambda h, p: _addrinfo(_PUBLIC), transport=_capture_transport(seen)
    )
    assert seen[0].url.host == _PUBLIC
    assert seen[0].headers["host"] == "example.com"
    assert "sni_hostname" not in seen[0].extensions


async def test_ipv6_pinned_host_is_bracketed():
    seen: list[httpx.Request] = []
    await safe_fetch_dataset_bytes(
        "https://example.com/f.csv",
        resolver=lambda h, p: _addrinfo("2606:2800:220:1:248:1893:25c8:1946"),
        transport=_capture_transport(seen),
    )
    assert str(seen[0].url).startswith("https://[2606:2800:220:1:248:1893:25c8:1946]/")


@pytest.mark.parametrize("private_ip", [_LOOPBACK, _METADATA, "10.1.2.3", "::1", "fd00::1"])
async def test_validation_lookup_to_private_space_is_refused_before_any_connection(private_ip: str):
    seen: list[httpx.Request] = []
    with pytest.raises(DatasetSecurityError):
        await safe_fetch_dataset_bytes(
            "https://example.com/f.csv",
            resolver=lambda h, p: _addrinfo(private_ip),
            transport=_capture_transport(seen),
        )
    assert seen == [], "no request may be sent for a refused address"


def test_validate_returns_deduplicated_validated_addresses():
    ips = validate_url_security(
        "https://example.com/x", resolver=lambda h, p: _addrinfo(_PUBLIC) + _addrinfo(_PUBLIC) + _addrinfo("1.1.1.1")
    )
    assert ips == [_PUBLIC, "1.1.1.1"]


def test_mixed_public_and_private_answers_are_refused():
    with pytest.raises(DatasetSecurityError):
        validate_url_security(
            "https://example.com/x", resolver=lambda h, p: _addrinfo(_PUBLIC) + _addrinfo(_LOOPBACK)
        )


def test_refresh_route_is_rate_limited():
    from bebshax.api.limiter import limiter

    assert "10 per 1 hour" in str(limiter._route_limits["bebshax.api.datasets.refresh_dataset"][0].limit)
