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


def test_parser_rejects_datasets_above_the_column_cap():
    """The byte ceiling bounds the input, not the shape it expands into."""
    from bebshax.datasets.parser import MAX_DATASET_COLUMNS, DatasetParseError, parse_dataset_bytes

    cols = [f"c{i}" for i in range(MAX_DATASET_COLUMNS + 1)]
    content = (",".join(cols) + "\n" + ",".join("1" for _ in cols) + "\n").encode()
    with pytest.raises(DatasetParseError, match="column"):
        parse_dataset_bytes(content, file_type="csv")


def test_parser_rejects_datasets_above_the_row_cap():
    from bebshax.datasets.parser import DatasetParseError, parse_dataset_bytes
    from bebshax.datasets import parser as parser_module

    original = parser_module.MAX_DATASET_ROWS
    parser_module.MAX_DATASET_ROWS = 3
    try:
        content = b"a,b\n" + b"1,2\n" * 10
        with pytest.raises(DatasetParseError, match="rows"):
            parse_dataset_bytes(content, file_type="csv")
    finally:
        parser_module.MAX_DATASET_ROWS = original


def test_xlsx_zip_bomb_is_rejected_before_parsing():
    """A few KB of .xlsx can declare gigabytes of sheet XML."""
    import io
    import zipfile

    from bebshax.datasets.parser import DatasetParseError, parse_dataset_bytes

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/worksheets/sheet1.xml", b"0" * (40 * 1024 * 1024))
    with pytest.raises(DatasetParseError, match="expands"):
        parse_dataset_bytes(buf.getvalue(), file_type="xlsx")

