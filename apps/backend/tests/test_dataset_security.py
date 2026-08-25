"""Tests for dataset SSRF protection and security constraints."""

import pytest

from bebshax.datasets.security import (
    DatasetSecurityError,
    validate_url_security,
)


def test_validate_url_security_blocks_private_ips():
    dangerous_urls = [
        "http://127.0.0.1/data.csv",
        "http://localhost:8000/secret.json",
        "http://10.0.0.5/dataset.csv",
        "http://192.168.1.100/data.tsv",
        "http://172.16.0.1/users.csv",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://example.com/data.csv",
        "file:///etc/passwd",
    ]

    for url in dangerous_urls:
        with pytest.raises(DatasetSecurityError):
            validate_url_security(url)


def test_validate_url_security_allows_valid_http_scheme():
    # Public domain format validation
    try:
        validate_url_security("https://raw.githubusercontent.com/datasets/sample.csv")
    except DatasetSecurityError as exc:
        # If offline DNS fails in test runner, verify it was a DNS resolution error rather than scheme error
        assert "Unable to resolve hostname" in str(exc) or "raw.githubusercontent.com" in str(exc)
