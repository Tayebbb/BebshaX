"""Security: password hashing (PBKDF2) and JWT tokens. B4-hardened."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, Optional, Union

from bebshax.config import get_settings

ALGORITHM = "HS256"

# The hash string encodes its own iteration count (`pbkdf2_sha256$<iters>$<salt>$<dk>`)
# and `verify_password` reads it back, so this constant only governs NEW hashes:
# raising it never invalidates stored passwords (they upgrade on the next reset).
# OWASP's 2023+ floor for PBKDF2-HMAC-SHA256 is 600_000.
PBKDF2_ITERATIONS = 600_000


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(s: str) -> bytes:
    s += "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=32)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64_encode(salt)}${_b64_encode(dk)}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        salt, expected = _b64_decode(parts[2]), _b64_decode(parts[3])
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), salt, int(parts[1]), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_access_token(
    user_id: Union[str, Dict[str, Any]], expires_delta: Optional[timedelta] = None,
    *, session_version: int = 0,
) -> str:
    """Sign path — ALWAYS current secret, never previous."""
    if isinstance(user_id, dict):
        user_id = str(user_id.get("sub", ""))
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(days=s.jwt_expire_days))
    payload = {
        "sub": user_id,
        "session_version": session_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
    }
    h_b64 = _b64_encode(
        json.dumps({"alg": ALGORITHM, "typ": "JWT"}, separators=(",", ":")).encode()
    )
    p_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(
        s.jwt_secret.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256
    ).digest()
    return f"{h_b64}.{p_b64}.{_b64_encode(sig)}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify path — tries current, then previous (grace window). Validates iss+aud."""
    s = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, s_b64 = parts
        keys = [s.jwt_secret] + (
            [s.jwt_secret_previous] if s.jwt_secret_previous else []
        )
        verified = False
        for key in keys:
            expected = hmac.new(
                key.encode(), f"{h_b64}.{p_b64}".encode(), hashlib.sha256
            ).digest()
            if hmac.compare_digest(expected, _b64_decode(s_b64)):
                verified = True
                break
        if not verified:
            return None
        payload = json.loads(_b64_decode(p_b64).decode())
        # exp is REQUIRED. Treating it as optional meant a token minted without
        # one never expired; `create_access_token` always sets it, so a token
        # lacking exp did not come from us and is rejected outright.
        exp = payload.get("exp")
        if exp is None or datetime.now(timezone.utc).timestamp() > exp:
            return None
        if payload.get("iss") != s.jwt_issuer:
            return None
        aud = payload.get("aud")
        if isinstance(aud, list):
            if s.jwt_audience not in aud:
                return None
        elif aud != s.jwt_audience:
            return None
        session_version = payload.get("session_version", 0)
        if type(session_version) is not int or session_version < 0:
            return None
        return payload
    except Exception:
        return None
