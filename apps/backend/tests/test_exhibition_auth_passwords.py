"""Password work-factor upgrades preserve existing encoded credentials."""

import base64
import hashlib

import pytest

from bebshax.auth.security import hash_password, verify_password


def test_new_password_hashes_use_600000_iterations() -> None:
    password = "ExhibitionPassword123!"

    encoded = hash_password(password)

    assert encoded.startswith("pbkdf2_sha256$600000$")
    assert verify_password(password, encoded) is True
    assert verify_password("WrongPassword456!", encoded) is False
    assert hash_password(password) != encoded


@pytest.mark.parametrize(
    "candidate,expected",
    [("LegacyPassword123!", True), ("WrongPassword456!", False), ("", False)],
)
def test_legacy_100000_iteration_passwords_remain_verifiable(
    candidate: str, expected: bool,
) -> None:
    salt = b"legacy-test-salt"
    digest = hashlib.pbkdf2_hmac("sha256", b"LegacyPassword123!", salt, 100_000, dklen=32)
    encoded_salt = base64.urlsafe_b64encode(salt).rstrip(b"=").decode("ascii")
    encoded_digest = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    encoded = f"pbkdf2_sha256$100000${encoded_salt}${encoded_digest}"

    assert verify_password(candidate, encoded) is expected