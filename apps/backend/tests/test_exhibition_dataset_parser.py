"""Adversarial input contracts for bounded, lossless dataset parsing."""

import json
from typing import Any

import pytest

from bebshax.datasets import parser
from bebshax.datasets.profiler import profile_dataset


@pytest.mark.parametrize(
    ("content", "file_type"),
    [
        (b" age , segment \n20,Student\n", "csv"),
        (b'[{" age ":20," segment ":"Student"}]', "json"),
        (b'{" age ":20," segment ":"Student"}\n', "jsonl"),
    ],
)
def test_normalized_headers_preserve_original_values(content: bytes, file_type: str) -> None:
    columns, rows = parser.parse_dataset_bytes(content, file_type=file_type)

    assert columns == ["age", "segment"]
    assert rows == [{"age": 20, "segment": "Student"}]


@pytest.mark.parametrize(
    "content",
    [b"age,age\n20,30\n", b"age, age \n20,30\n", b"age,\n20,30\n", b"age\n20,30\n"],
)
def test_ambiguous_or_excess_csv_fields_are_rejected(content: bytes) -> None:
    with pytest.raises(parser.DatasetParseError):
        parser.parse_dataset_bytes(content, file_type="csv")


@pytest.mark.parametrize("file_type", ["json", "jsonl"])
def test_column_cap_is_enforced_before_dense_normalization(
    file_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [{"first": 1}, {"second": 2}]
    content = (
        json.dumps(records)
        if file_type == "json"
        else "\n".join(json.dumps(record) for record in records)
    ).encode()
    cast_values: list[Any] = []
    original_cast = parser._cast_value

    def counted_cast(value: Any) -> Any:
        cast_values.append(value)
        return original_cast(value)

    monkeypatch.setattr(parser, "MAX_DATASET_COLUMNS", 1)
    monkeypatch.setattr(parser, "_cast_value", counted_cast)

    with pytest.raises(parser.DatasetParseError, match="column"):
        parser.parse_dataset_bytes(content, file_type=file_type)

    assert cast_values == []


@pytest.mark.parametrize("content", [b"value\n1e309\n", b"value\n-inf\n"])
def test_nonfinite_numbers_do_not_enter_profile_statistics(content: bytes) -> None:
    with pytest.raises(parser.DatasetParseError, match="finite"):
        columns, rows = parser.parse_dataset_bytes(content, file_type="csv")
        json.dumps(profile_dataset(columns, rows), allow_nan=False)