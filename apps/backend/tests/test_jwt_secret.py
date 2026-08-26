"""B4 regression guard. Must FAIL before fix, PASS after."""
import base64
import hashlib
import hmac
import importlib
import json
import time
import pytest

BURNED = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"


def _clear():
    import bebshax.config as c

    c.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _restore_config_after_test():
    yield
    _clear()
    try:
        import bebshax.config as c

        importlib.reload(c)
    except Exception:
        pass
    _clear()


def _token(payload, secret):
    h = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    s = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{base64.urlsafe_b64encode(s).rstrip(b'=').decode()}"


def test_empty_secret_exits(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "")
    _clear()
    import bebshax.config as c

    with pytest.raises(SystemExit):
        importlib.reload(c)
    _clear()


def test_short_secret_exits(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", "tooshort")
    _clear()
    import bebshax.config as c

    with pytest.raises(SystemExit):
        importlib.reload(c)
    _clear()


def test_burned_secret_exits(monkeypatch):
    monkeypatch.setenv("BEBSHAX_JWT_SECRET", BURNED)
    _clear()
    import bebshax.config as c

    with pytest.raises(SystemExit):
        importlib.reload(c)
    _clear()


def test_missing_aud_rejected():
    from bebshax.config import get_settings as gs

    s = gs()
    t = _token(
        {
            "sub": "x",
            "iss": s.jwt_issuer,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        s.jwt_secret,
    )
    from bebshax.auth.security import decode_access_token

    assert decode_access_token(t) is None, "Accepted token without aud"


def test_wrong_issuer_rejected():
    from bebshax.config import get_settings as gs

    s = gs()
    t = _token(
        {
            "sub": "x",
            "iss": "evil",
            "aud": s.jwt_audience,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        s.jwt_secret,
    )
    from bebshax.auth.security import decode_access_token

    assert decode_access_token(t) is None, "Accepted token with wrong iss"


def test_wrong_aud_rejected():
    from bebshax.config import get_settings as gs

    s = gs()
    t = _token(
        {
            "sub": "x",
            "iss": s.jwt_issuer,
            "aud": "wrong",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        s.jwt_secret,
    )
    from bebshax.auth.security import decode_access_token

    assert decode_access_token(t) is None, "Accepted token with wrong aud"


def test_burned_key_token_rejected(monkeypatch):
    monkeypatch.delenv("BEBSHAX_JWT_SECRET_PREVIOUS", raising=False)
    _clear()
    from bebshax.config import get_settings as gs

    s = gs()
    t = _token(
        {
            "sub": "victim",
            "iss": s.jwt_issuer,
            "aud": s.jwt_audience,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        BURNED,
    )
    import bebshax.auth.security as sec

    importlib.reload(sec)
    assert sec.decode_access_token(t) is None, "Accepted burned-key token post-grace"
    _clear()


def test_valid_token_still_works():
    from bebshax.auth.security import create_access_token, decode_access_token

    r = decode_access_token(create_access_token("usr_test"))
    assert r and r["sub"] == "usr_test"
