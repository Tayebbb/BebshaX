"""Shared rate limiter instance for BebshaX endpoints.

Deployment posture (settings-driven, secure defaults):

- storage: slowapi's in-memory store unless ``BEBSHAX_RATE_LIMIT_STORAGE_URI``
  points at a shared backend. In-memory counters are per-process, so a
  multi-worker deployment MUST set this or each worker enforces its own copy
  of every limit.
- client key: the socket peer address. ``X-Forwarded-For`` is only honoured
  when ``BEBSHAX_RATE_LIMIT_TRUST_FORWARDED_FOR`` is explicitly enabled for a
  deployment behind exactly one trusted proxy. We take the LAST hop: proxies
  append the peer they saw, so the last entry is the only one our own proxy
  wrote — earlier hops are attacker-controlled under the common append
  configs (nginx ``$proxy_add_x_forwarded_for``, ALB, CDNs) and would let
  clients mint fresh buckets. The hop must parse as an IP or we fall back to
  the socket address, keeping junk out of the limiter keyspace.
"""
import ipaddress

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from bebshax.config import get_settings


def _hop_ip(hop: str) -> str | None:
    """Parse an XFF hop into a validated IP, tolerating proxy port suffixes.

    Handles "1.2.3.4", "1.2.3.4:51423" (IIS/ARR style), "2001:db8::1", and
    "[2001:db8::1]:443". Returns None for anything that isn't an IP.
    """
    candidate = hop
    if candidate.startswith("[") and "]" in candidate:  # bracketed IPv6[:port]
        candidate = candidate[1 : candidate.index("]")]
    elif candidate.count(":") == 1:  # IPv4:port (bare IPv6 has ≥2 colons)
        candidate = candidate.split(":", 1)[0]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _client_key(request: Request) -> str:
    settings = get_settings()
    if settings.rate_limit_trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.rsplit(",", 1)[-1].strip()
        if last:
            ip = _hop_ip(last)
            if ip is not None:
                return ip
            # not an IP — never key limits on attacker-typed strings
    return get_remote_address(request)


def _build_limiter() -> Limiter:
    storage_uri = get_settings().rate_limit_storage_uri
    if storage_uri:
        return Limiter(key_func=_client_key, storage_uri=storage_uri)
    return Limiter(key_func=_client_key)


limiter = _build_limiter()
