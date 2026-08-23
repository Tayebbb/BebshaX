"""Security utilities: password hashing (PBKDF2-HMAC-SHA256) and JWT tokens."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Dict, Optional

# Secret key used for signing JWTs (in production, loaded from environment)
JWT_SECRET = "bebshax-super-secret-jwt-signing-key-2026-auth-v1"
JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64_decode(data_str: str) -> bytes:
    padding = 4 - (len(data_str) % 4)
    if padding != 4:
        data_str += "=" * padding
    return base64.urlsafe_b64decode(data_str.encode("ascii"))


def hash_password(password: str) -> str:
    """Hash a password using salted PBKDF2-HMAC-SHA256 (100,000 rounds)."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000,
        dklen=32,
    )
    salt_b64 = _b64_encode(salt)
    dk_b64 = _b64_encode(dk)
    return f"pbkdf2_sha256$100000${salt_b64}${dk_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a stored hashed password."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = _b64_decode(parts[2])
        expected_dk = _b64_decode(parts[3])
        actual_dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_dk),
        )
        return hmac.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    secret_key: str = JWT_SECRET,
) -> str:
    """Create an HMAC-SHA256 signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp()), "iat": int(now.timestamp())})

    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_json = json.dumps(to_encode, separators=(",", ":")).encode("utf-8")

    header_b64 = _b64_encode(header_json)
    payload_b64 = _b64_encode(payload_json)

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(
        secret_key.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    sig_b64 = _b64_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(
    token: str,
    secret_key: str = JWT_SECRET,
) -> Optional[Dict[str, Any]]:
    """Decode and verify an HMAC-SHA256 JWT access token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64_decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_json = _b64_decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)

        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None

        return payload
    except Exception:
        return None
