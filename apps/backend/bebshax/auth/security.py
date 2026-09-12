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
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("Password exceeds the supported bound")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=32)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64_encode(salt)}${_b64_encode(dk)}"


def _password_parts(hashed: str) -> tuple[bytes, bytes, int] | None:
    try:
        if not isinstance(hashed, str) or len(hashed) > 255:
            return None
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return None
        if not parts[1].isascii() or not parts[1].isdigit() or len(parts[1]) > 6:
            return None
        iterations = int(parts[1])
        if not 1 <= iterations <= PBKDF2_ITERATIONS:
            return None
        salt, expected = _b64_decode(parts[2]), _b64_decode(parts[3])
        if len(salt) != 16 or len(expected) != 32:
            return None
        return salt, expected, iterations
    except (ValueError, TypeError):
        return None


def password_hash_usable(hashed: str | None) -> bool:
    return hashed is not None and _password_parts(hashed) is not None


def verify_password(plain: str, hashed: str) -> bool:
    parts = _password_parts(hashed)
    if parts is None or not isinstance(plain, str) or len(plain) > 128:
        return False
    salt, expected, iterations = parts
    try:
        actual = hashlib.pbkdf2_hmac(
            "sha256", plain.encode(), salt, iterations, dklen=32,
        )
        if iterations < PBKDF2_ITERATIONS:
            hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, PBKDF2_ITERATIONS - iterations, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(
    user_id: Union[str, Dict[str, Any]], expires_delta: Optional[timedelta] = None,
    *, session_version: int = 0, session_id: str | None = None,
) -> str:
    """Sign path — ALWAYS current secret, never previous."""
    if isinstance(user_id, dict):
        user_id = str(user_id.get("sub", ""))
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta if expires_delta is not None else timedelta(days=s.jwt_expire_days))
    payload = {
        "sub": user_id,
        "session_version": session_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
    }
    if session_id is not None:
        payload["jti"] = session_id
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
    if not token or len(token) > 4096:
        return None
    s = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        h_b64, p_b64, s_b64 = parts
        header = json.loads(_b64_decode(h_b64).decode())
        if not isinstance(header, dict) or header.get("alg") != ALGORITHM or header.get("typ") != "JWT":
            return None
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
        if not isinstance(payload, dict):
            return None
        subject = payload.get("sub")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 64:
            return None
        # exp is REQUIRED. Treating it as optional meant a token minted without
        # one never expired; `create_access_token` always sets it, so a token
        # lacking exp did not come from us and is rejected outright.
        exp = payload.get("exp")
        now = datetime.now(timezone.utc).timestamp()
        issued_at = payload.get("iat")
        if type(exp) is not int or now >= exp:
            return None
        if type(issued_at) is not int or issued_at < 0 or issued_at > now + 30 or issued_at >= exp:
            return None
        not_before = payload.get("nbf")
        if not_before is not None and (type(not_before) is not int or not_before < 0 or not_before > now):
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
        if "jti" in payload and (
            not isinstance(payload["jti"], str) or not 1 <= len(payload["jti"]) <= 64
        ):
            return None
        return payload
    except Exception:
        return None
