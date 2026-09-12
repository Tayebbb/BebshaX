"""Neon session verification uses only a trusted HTTPS server-side endpoint."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from bebshax.api import auth as auth_api


@pytest.fixture
def neon_transport(identity_state, monkeypatch) -> SimpleNamespace:
    state = SimpleNamespace(calls=[], response=httpx.Response(200, json={
        "user": {"email": "owner@example.test", "emailVerified": True},
    }))
    original_client = httpx.AsyncClient

    def verify_request(request: httpx.Request) -> httpx.Response:
        state.calls.append(request)
        return state.response

    def client_factory(**kwargs) -> httpx.AsyncClient:
        return original_client(transport=httpx.MockTransport(verify_request), **kwargs)

    monkeypatch.setattr(auth_api.httpx, "AsyncClient", client_factory)
    identity_state.settings.neon_auth_url = "https://identity.example.test/auth"
    return state


@pytest.mark.parametrize("url", [
    "http://identity.example.test/auth", "https://identity.example.test/auth?token=private",
    "https://identity.example.test/auth#private", "https://user:private@identity.example.test/auth",
    "https://identity.example.test:bad/auth", "https://identity.example.test/\\foreign",
    "https://identity.example.test/\nauth",
])
async def test_neon_rejects_unsafe_configuration_before_sending_credentials(identity_state, neon_transport, url) -> None:
    identity_state.settings.neon_auth_url = url
    with pytest.raises(HTTPException) as rejected:
        await auth_api.verify_neon_token("synthetic-session-proof")
    assert rejected.value.status_code == 503
    assert neon_transport.calls == []
    assert "private" not in rejected.value.detail


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
async def test_neon_service_failure_is_not_reported_as_invalid_credentials(neon_transport, status_code, caplog) -> None:
    neon_transport.response = httpx.Response(status_code, text="private-upstream-failure")
    with pytest.raises(HTTPException) as rejected:
        await auth_api.verify_neon_token("synthetic-session-proof")
    assert rejected.value.status_code == 503
    assert "private-upstream-failure" not in rejected.value.detail
    assert "synthetic-session-proof" not in caplog.text


async def test_neon_token_is_sent_in_header_to_exact_configured_verifier(neon_transport) -> None:
    result = await auth_api.verify_neon_token("synthetic-session-proof")
    assert result["user"]["email"] == "owner@example.test"
    assert len(neon_transport.calls) == 1
    request = neon_transport.calls[0]
    assert str(request.url) == "https://identity.example.test/auth/get-session"
    assert request.headers["Authorization"] == "Bearer synthetic-session-proof"
    assert not request.content


async def test_neon_redirect_is_never_followed_with_session_proof(neon_transport) -> None:
    neon_transport.response = httpx.Response(302, headers={"Location": "https://foreign.example.test"})
    with pytest.raises(HTTPException) as rejected:
        await auth_api.verify_neon_token("synthetic-session-proof")
    assert rejected.value.status_code == 401
    assert len(neon_transport.calls) == 1