"""Deep-audit regressions for the Sazid track (2026-08-27).

Each test here corresponds to a defect found by verifying the 11 audit items
against the code rather than against their own DONE notes. They exist so the
same gaps cannot reopen silently.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from bebshax.auth.security import create_access_token, decode_access_token
from bebshax.config import Settings, get_settings


def _claims(token: str) -> dict:
    part = token.split(".")[1]
    part += "=" * ((4 - len(part) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


def test_token_lifetime_matches_what_the_api_reports():
    """B4/M7: tokens lived 365 days while AuthResponse claimed 7.

    The response field is now derived from the same setting that signs the
    token, so the two cannot drift apart again.
    """
    from bebshax.api.auth import AuthResponse, UserProfileResponse

    settings = get_settings()
    claims = _claims(create_access_token("usr_probe"))
    actual_days = (claims["exp"] - claims["iat"]) / 86400

    assert actual_days == pytest.approx(settings.jwt_expire_days, abs=0.01)

    response = AuthResponse(
        access_token="t",
        user=UserProfileResponse(
            id="u", email="a@b.co", full_name="A", is_active=True,
            is_verified=True, auth_provider="email",
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        ),
    )
    assert response.expires_in_days == settings.jwt_expire_days, (
        "AuthResponse must report the lifetime it actually issued"
    )


def test_token_lifetime_is_not_a_year():
    """A year-long bearer token in localStorage is the M7 threat, amplified."""
    claims = _claims(create_access_token("usr_probe"))
    assert (claims["exp"] - claims["iat"]) / 86400 <= 30


def test_token_without_exp_is_rejected():
    """A missing exp used to mean 'never expires' on the verify path."""
    import hashlib
    import hmac

    settings = get_settings()

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    # Correctly signed, but carries no exp claim.
    payload = b64(json.dumps({
        "sub": "usr_forever",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }).encode())
    sig = hmac.new(
        settings.jwt_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()

    assert decode_access_token(f"{header}.{payload}.{b64(sig)}") is None


def test_expired_token_still_rejected():
    """Guard the fix above did not break ordinary expiry."""
    token = create_access_token("usr_probe", expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None


def test_valid_token_still_accepted():
    token = create_access_token("usr_probe")
    claims = decode_access_token(token)
    assert claims is not None and claims["sub"] == "usr_probe"


@pytest.mark.parametrize(
    "environment,expected",
    [("production", True), ("staging", True), ("development", False), ("local", False)],
)
def test_email_verification_enforced_by_environment(environment, expected):
    """H9: sending a link is meaningless if unverified accounts can sign in.

    Enforcement follows `environment` so the offline demo drill keeps working
    while real deployments are gated.
    """
    settings = Settings(
        environment=environment,
        jwt_secret="test_secret_at_least_32_characters_long_12345",
        resend_api_key="re_test_key",
        # Hosted envs now also require a verified sender (production-readiness
        # audit); this test's subject is verification enforcement, not sender config.
        email_from_address="noreply@example.com",
    )
    assert settings.email_verification_enforced is expected


def test_email_verification_enforcement_can_be_overridden():
    settings = Settings(
        environment="development",
        require_email_verification=True,
        jwt_secret="test_secret_at_least_32_characters_long_12345",
    )
    assert settings.email_verification_enforced is True


def test_save_persona_requires_explicit_owner():
    """B6: the old default put forgotten-owner personas in the public pool."""
    import inspect

    from bebshax.persona.store import create_business, save_persona
    from bebshax.tenancy import PUBLIC_OWNER_IDS

    for fn in (save_persona, create_business):
        param = inspect.signature(fn).parameters["owner_id"]
        assert param.default is inspect.Parameter.empty, (
            f"{fn.__name__} must not default owner_id — the old default "
            f"({PUBLIC_OWNER_IDS[0]}) is in the shared pool and silently "
            "published rows to every user"
        )
