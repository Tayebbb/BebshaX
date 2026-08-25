"""Safe dataset parser supporting CSV, TSV, JSON, JSONL, and structured tables."""

from __future__ import annotations

import csv
import io
import json
from typing import Any


class DatasetParseError(Exception):
    """Raised when dataset content cannot be parsed."""
    pass


def detect_format(content: bytes, filename: str = "", content_type: str = "") -> str:
    """Detect dataset format from file name, content-type header, or magic bytes."""
    fname_lower = filename.lower()
    ctype_lower = content_type.lower()

    if fname_lower.endswith(".json") or "application/json" in ctype_lower:
        return "json"
    if fname_lower.endswith(".jsonl") or "application/x-ndjson" in ctype_lower:
        return "jsonl"
    if fname_lower.endswith(".tsv") or "text/tab-separated-values" in ctype_lower:
        return "tsv"
    if fname_lower.endswith(".xlsx") or fname_lower.endswith(".xls") or "spreadsheet" in ctype_lower:
        return "xlsx"
    if fname_lower.endswith(".csv") or "text/csv" in ctype_lower:
        return "csv"

    # Inspect first few non-empty characters
    snippet = content[:1024].decode("utf-8", errors="ignore").strip()
    if snippet.startswith("[") or (snippet.startswith("{") and "\n" not in snippet):
        return "json"
    if snippet.startswith("{") and "\n" in snippet:
        return "jsonl"
    if "\t" in snippet.splitlines()[0] if snippet.splitlines() else False:
        return "tsv"
    return "csv"


def parse_dataset_bytes(
    content: bytes,
    file_type: str | None = None,
    filename: str = "",
    content_type: str = "",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse raw dataset bytes into column names and list of row dicts.
    
    Returns:
        (columns: list[str], rows: list[dict[str, Any]])
    """
    if not content:
        raise DatasetParseError("Dataset content is empty.")

    detected_type = file_type or detect_format(content, filename=filename, content_type=content_type)

    try:
        if detected_type == "json":
            return _parse_json(content)
        elif detected_type == "jsonl":
            return _parse_jsonl(content)
        elif detected_type == "tsv":
            return _parse_delimited(content, delimiter="\t")
        elif detected_type == "xlsx":
            return _parse_xlsx(content)
        else:
            return _parse_delimited(content, delimiter=",")
    except Exception as exc:
        if isinstance(exc, DatasetParseError):
            raise
        raise DatasetParseError(f"Failed to parse {detected_type.upper()} dataset: {exc}") from exc


def _parse_delimited(content: bytes, delimiter: str = ",") -> tuple[list[str], list[dict[str, Any]]]:
    text = content.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise DatasetParseError("Delimited text dataset contains no data rows.")

    # Check for automatic delimiter detection if ambiguous
    first_line = lines[0]
    if delimiter == "," and "\t" in first_line and first_line.count("\t") > first_line.count(","):
        delimiter = "\t"
    elif delimiter == "," and ";" in first_line and first_line.count(";") > first_line.count(","):
        delimiter = ";"
    elif delimiter == "," and "|" in first_line and first_line.count("|") > first_line.count(","):
        delimiter = "|"

    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise DatasetParseError("Dataset header is missing or invalid.")

    clean_columns = [str(f).strip() for f in fieldnames if f is not None and str(f).strip()]
    if not clean_columns:
        raise DatasetParseError("No valid columns found in dataset header.")

    rows: list[dict[str, Any]] = []
    for row in reader:
        clean_row: dict[str, Any] = {}
        for col in clean_columns:
            val = row.get(col)
            clean_row[col] = _cast_value(val)
        rows.append(clean_row)

    if not rows:
        raise DatasetParseError("Dataset contains headers but 0 data rows.")

    return clean_columns, rows


def _parse_json(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    text = content.decode("utf-8-sig", errors="replace")
    data = json.loads(text)

    if isinstance(data, dict):
        # Look for common container keys: "data", "records", "rows", "items", "results"
        for key in ("data", "records", "rows", "items", "results", "personas", "users", "observations"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        raise DatasetParseError("JSON dataset must be an array of records/objects.")

    if not data:
        raise DatasetParseError("JSON dataset is an empty array.")

    # Collect all unique keys across all records
    cols_set: dict[str, None] = {}
    for item in data:
        if isinstance(item, dict):
            for k in item.keys():
                cols_set[str(k).strip()] = None

    columns = list(cols_set.keys())
    if not columns:
        raise DatasetParseError("JSON objects have no valid keys/fields.")

    rows: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            row = {col: _cast_value(item.get(col)) for col in columns}
            rows.append(row)

    return columns, rows


def _parse_jsonl(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    text = content.decode("utf-8-sig", errors="replace")
    rows: list[dict[str, Any]] = []
    cols_set: dict[str, None] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                for k in item.keys():
                    cols_set[str(k).strip()] = None
                rows.append(item)
        except json.JSONDecodeError:
            continue

    if not rows:
        raise DatasetParseError("JSONL dataset contains no valid JSON object lines.")

    columns = list(cols_set.keys())
    normalized_rows = [{col: _cast_value(r.get(col)) for col in columns} for r in rows]
    return columns, normalized_rows


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content))
        columns = [str(c).strip() for c in df.columns]
        records = df.to_dict(orient="records")
        clean_records = [{col: _cast_value(r.get(col)) for col in columns} for r in records]
        return columns, clean_records
    except Exception as exc:
        raise DatasetParseError(f"Excel parsing requires openpyxl or failed: {exc}")


def _cast_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (int, float, bool, list, dict)):
        return val
    s = str(val).strip()
    if s == "" or s.lower() in ("null", "none", "nan", "na", "n/a"):
        return None
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # Try integer
    try:
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    return s
