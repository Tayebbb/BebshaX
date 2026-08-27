"""Rate limiter deployment-config tests (storage URI + proxy key trust).

The audit point: slowapi's default is per-process memory storage keyed by
socket address. That is correct for the single-worker topology but silently
wrong behind multiple workers or a reverse proxy. These tests pin the two
settings-driven escape hatches and their secure defaults.
"""

import pytest
from starlette.requests import Request

from bebshax.api.limiter import _build_limiter, _client_key
from bebshax.config import get_settings


def _request(client_host: str, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    return Request(scope)


@pytest.fixture()
def clean_settings(monkeypatch):
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_default_key_is_socket_address_and_xff_is_ignored(clean_settings):
    """Untrusted default: a spoofed X-Forwarded-For must not mint a new bucket."""
    clean_settings.delenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", raising=False)
    req = _request("10.0.0.7", {"X-Forwarded-For": "1.2.3.4, 10.0.0.7"})
    assert _client_key(req) == "10.0.0.7"


def test_trusted_proxy_uses_last_forwarded_hop(clean_settings):
    """Append-mode proxies put the peer they saw LAST — that's the only hop we wrote."""
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    req = _request("10.0.0.7", {"X-Forwarded-For": "6.6.6.6, 1.2.3.4"})
    assert _client_key(req) == "1.2.3.4"


def test_trusted_proxy_spoofed_first_hop_cannot_mint_buckets(clean_settings):
    """Client-sent 'X-Forwarded-For: junk' arrives as 'junk, <real-ip>' — junk must lose."""
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    req = _request("10.0.0.7", {"X-Forwarded-For": "i-am-not-an-ip, 1.2.3.4"})
    assert _client_key(req) == "1.2.3.4"


def test_trusted_proxy_non_ip_hop_falls_back_to_socket(clean_settings):
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    req = _request("10.0.0.7", {"X-Forwarded-For": "totally-junk"})
    assert _client_key(req) == "10.0.0.7"


def test_trusted_proxy_strips_port_suffixes(clean_settings):
    """IIS/ARR-style 'ip:port' hops must not collapse everyone onto one bucket."""
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    req = _request("10.0.0.7", {"X-Forwarded-For": "1.2.3.4:51423"})
    assert _client_key(req) == "1.2.3.4"
    req6 = _request("10.0.0.7", {"X-Forwarded-For": "[2001:db8::1]:443"})
    assert _client_key(req6) == "2001:db8::1"


def test_trusted_proxy_with_missing_header_falls_back_to_socket(clean_settings):
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR", "true")
    req = _request("10.0.0.7")
    assert _client_key(req) == "10.0.0.7"


def test_storage_uri_setting_reaches_the_limiter(clean_settings):
    clean_settings.setenv("BEBSHAX_RATE_LIMIT_STORAGE_URI", "memory://shared-test")
    limiter = _build_limiter()
    # slowapi has no public storage accessor; `_storage_uri` is pinned against
    # the locked slowapi version — if an upgrade breaks this line, re-check the
    # attr, not the behavior.
    assert limiter._storage_uri == "memory://shared-test"


def test_default_storage_is_in_memory(clean_settings):
    clean_settings.delenv("BEBSHAX_RATE_LIMIT_STORAGE_URI", raising=False)
    limiter = _build_limiter()
    assert limiter._storage_uri in (None, "memory://")
