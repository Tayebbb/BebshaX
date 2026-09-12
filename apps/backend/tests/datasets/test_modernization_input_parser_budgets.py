"""Small adversarial fixtures prove limits precede expensive materialization."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from typing import Any

import pytest

from bebshax.datasets import parser


@pytest.mark.parametrize("file_type", ["json", "jsonl"])
@pytest.mark.parametrize("budget", ["cells", "normalized_bytes"])
def test_sparse_records_are_rejected_before_dense_casting(
    monkeypatch: pytest.MonkeyPatch, file_type: str, budget: str,
) -> None:
    records = [{f"column_{index}_" + "a" * 30: index} for index in range(4)]
    content = (json.dumps(records) if file_type == "json" else "\n".join(map(json.dumps, records))).encode()
    monkeypatch.setattr(parser, "MAX_DATASET_CELLS", 8 if budget == "cells" else 1000, raising=False)
    monkeypatch.setattr(parser, "MAX_DATASET_NORMALIZED_BYTES", 300 if budget == "normalized_bytes" else 100_000, raising=False)
    casts = []
    original_cast = parser._cast_value

    def counted_cast(value: Any) -> Any:
        casts.append(value)
        return original_cast(value)

    monkeypatch.setattr(parser, "_cast_value", counted_cast)
    with pytest.raises(parser.DatasetParseError, match="cell|normalized") as refused:
        parser.parse_dataset_bytes(content, file_type=file_type)

    assert refused.value.error_code == "dataset_limits_exceeded"
    assert refused.value.status_code == 413
    assert casts == []


@pytest.mark.parametrize("file_type", ["json", "jsonl"])
@pytest.mark.parametrize("budget", ["depth", "nodes"])
def test_json_complexity_is_checked_before_json_decode(
    monkeypatch: pytest.MonkeyPatch, file_type: str, budget: str,
) -> None:
    record = b'{"value":' + (b"[" * 8 + b"0" + b"]" * 8 if budget == "depth" else b"[0,0,0,0,0,0,0,0]") + b"}"
    content = b"[" + record + b"]" if file_type == "json" else record + b"\n"
    monkeypatch.setattr(parser, "MAX_DATASET_NESTING", 4 if budget == "depth" else 16, raising=False)
    monkeypatch.setattr(parser, "MAX_DATASET_NODES", 5 if budget == "nodes" else 1000, raising=False)
    decode_calls = []
    original_loads = parser.json.loads

    def counted_loads(*args, **kwargs):
        decode_calls.append(True)
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(parser.json, "loads", counted_loads)
    with pytest.raises(parser.DatasetParseError, match="nesting|complexity"):
        parser.parse_dataset_bytes(content, file_type=file_type)

    assert decode_calls == []


@pytest.mark.parametrize("file_type", ["json", "jsonl", "csv", "tsv"])
def test_normalized_text_byte_budget_precedes_decoder_allocation(monkeypatch, file_type: str) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_NORMALIZED_BYTES", 100)
    value = "\u00e9" * 30
    content = (json.dumps([{"value": value}], ensure_ascii=False) if file_type == "json" else
               json.dumps({"value": value}, ensure_ascii=False) if file_type == "jsonl" else
               "value\n" + value + "\n").encode()
    decodes = []
    original_loads = parser.json.loads
    original_reader = parser.csv.reader

    def counted_loads(*args, **kwargs):
        decodes.append(True)
        return original_loads(*args, **kwargs)

    def counted_reader(*args, **kwargs):
        decodes.append(True)
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(parser.json, "loads", counted_loads)
    monkeypatch.setattr(parser.csv, "reader", counted_reader)
    with pytest.raises(parser.DatasetParseError, match="normalized"):
        parser.parse_dataset_bytes(content, file_type=file_type)
    assert decodes == []


def test_delimited_width_is_checked_before_csv_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_COLUMNS", 2)
    reader_calls = []
    original_reader = parser.csv.reader

    def counted_reader(*args, **kwargs):
        reader_calls.append(True)
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(parser.csv, "reader", counted_reader)
    with pytest.raises(parser.DatasetParseError, match="column"):
        parser.parse_dataset_bytes(b"a,b,c\n1,2,3\n", file_type="csv")

    assert reader_calls == []


@pytest.mark.parametrize("file_type", ["csv", "tsv"])
def test_delimited_aggregate_cells_are_checked_before_casting(monkeypatch, file_type: str) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_CELLS", 3, raising=False)
    separator = "," if file_type == "csv" else "\t"
    content = separator.join(["first", "second"]) + "\n" + (separator.join(["1", "2"]) + "\n") * 3
    casts = []
    original_cast = parser._cast_value

    def counted_cast(value):
        casts.append(value)
        return original_cast(value)

    monkeypatch.setattr(parser, "_cast_value", counted_cast)
    with pytest.raises(parser.DatasetParseError, match="cell"):
        parser.parse_dataset_bytes(content.encode(), file_type=file_type)

    assert casts == []


@pytest.mark.parametrize(
    ("content", "file_type"),
    [
        (b'{"value":1}\nnot-json\n{"value":2}\n', "jsonl"),
        (b'[{"value":1},7,{"value":2}]', "json"),
        (b'{"value":1}\n7\n', "jsonl"),
        (b'[{"value":1,"value":2}]', "json"),
        (b'[{"value":{"hidden":1e999}}]', "json"),
        (b"value\n\xff\n", "csv"),
    ],
)
def test_invalid_data_is_rejected_as_a_whole(content: bytes, file_type: str) -> None:
    with pytest.raises(parser.DatasetParseError):
        parser.parse_dataset_bytes(content, file_type=file_type)


@pytest.mark.parametrize("file_type", ["json", "jsonl", "csv", "tsv"])
def test_valid_formats_preserve_rows_and_tail(file_type: str) -> None:
    records = [{"name": "Alpha", "value": 2}, {"name": "Tail retained", "value": 3}]
    content = {
        "json": json.dumps({"data": records}).encode(),
        "jsonl": "\n".join(map(json.dumps, records)).encode(),
        "csv": b'name,value\nAlpha,2\nTail retained,3\n',
        "tsv": b'name\tvalue\nAlpha\t2\nTail retained\t3\n',
    }[file_type]

    columns, rows = parser.parse_dataset_bytes(content, file_type=file_type)

    assert columns == ["name", "value"]
    assert rows == records


def test_csv_quotes_and_embedded_newlines_remain_valid(monkeypatch) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_COLUMNS", 2)
    monkeypatch.setattr(parser, "MAX_DATASET_ROWS", 2)
    columns, rows = parser.parse_dataset_bytes(
        b'name,value\r\n"one, two",1\r\n"line one\nline ""two""",2\r\n', file_type="csv",
    )
    assert columns == ["name", "value"]
    assert rows == [{"name": "one, two", "value": 1}, {"name": 'line one\nline "two"', "value": 2}]


def _xlsx(sheet_xml: str, *, shared_strings: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>''')
        archive.writestr("_rels/.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr("xl/workbook.xml", '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr("xl/_rels/workbook.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>''')
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/sharedStrings.xml", shared_strings or '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="0" uniqueCount="0"/>')
    return buffer.getvalue()


def test_xlsx_sparse_dimensions_are_rejected_before_workbook_load(monkeypatch) -> None:
    content = _xlsx('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:XFD1048576"/><sheetData/></worksheet>')
    loads = []

    def counted_load(*args, **kwargs):
        loads.append(True)
        raise AssertionError("Unsafe workbook reached the materializing reader")

    monkeypatch.setattr(parser, "_load_xlsx_workbook", counted_load, raising=False)
    with pytest.raises(parser.DatasetParseError, match="column|rows|cell"):
        parser.parse_dataset_bytes(content, file_type="xlsx")

    assert loads == []


def test_valid_xlsx_archive_and_shared_strings_pass_preflight() -> None:
    content = _xlsx(
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:A2"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>value</t></is></c></row><row r="2"><c r="A2" t="s"><v>0</v></c></row></sheetData></worksheet>',
        shared_strings='<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Tail retained</t></si></sst>',
    )
    parser._assert_xlsx_is_not_a_zip_bomb(content)


@pytest.mark.parametrize("corruption", ["compression", "deflate"])
def test_corrupt_xlsx_compression_is_a_controlled_parse_refusal(corruption: str) -> None:
    content = bytearray(_xlsx('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'))
    if corruption == "compression":
        central = content.find(b"PK\x01\x02")
        struct.pack_into("<H", content, central + 10, 99)
    else:
        name_length, extra_length = struct.unpack_from("<HH", content, 26)
        compressed_start = 30 + name_length + extra_length
        content[compressed_start] = 0x07
    with pytest.raises(parser.DatasetParseError) as refused:
        parser.parse_dataset_bytes(bytes(content), file_type="xlsx")
    assert refused.value.status_code == 422
    assert refused.value.error_code == "dataset_unparseable"


def test_xlsx_valid_inline_strings_preserve_trimmed_header_values() -> None:
    pytest.importorskip("openpyxl", reason="Optional Excel reader is absent; package installation is not authorized")
    content = _xlsx('''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:B3"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t> name </t></is></c><c r="B1" t="inlineStr"><is><t>value</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Alpha</t></is></c><c r="B2"><v>2</v></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>Tail retained</t></is></c><c r="B3"><v>3</v></c></row></sheetData></worksheet>''')
    columns, rows = parser.parse_dataset_bytes(content, file_type="xlsx")
    assert columns == ["name", "value"]
    assert rows == [{"name": "Alpha", "value": 2}, {"name": "Tail retained", "value": 3}]


def test_xlsx_entity_declarations_are_refused() -> None:
    content = _xlsx('''<?xml version="1.0"?><!DOCTYPE worksheet [<!ENTITY input "expanded">]><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&input;</t></is></c></row></sheetData></worksheet>''')
    with pytest.raises(parser.DatasetParseError, match="declaration|entity|unsafe"):
        parser.parse_dataset_bytes(content, file_type="xlsx")


def test_xlsx_shared_string_amplification_is_rejected_before_workbook_load(monkeypatch) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_NORMALIZED_BYTES", 500, raising=False)
    data_rows = ''.join(f'<row r="{index}"><c r="A{index}" t="s"><v>0</v></c></row>' for index in range(2, 9))
    content = _xlsx(
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:A8"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>value</t></is></c></row>' + data_rows + '</sheetData></worksheet>',
        shared_strings='<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>' + 'x' * 100 + '</t></si></sst>',
    )
    loads = []

    def counted_load(*args, **kwargs):
        loads.append(True)
        raise AssertionError("Expanded shared strings reached the materializing reader")

    monkeypatch.setattr(parser, "_load_xlsx_workbook", counted_load, raising=False)
    with pytest.raises(parser.DatasetParseError, match="normalized"):
        parser.parse_dataset_bytes(content, file_type="xlsx")

    assert loads == []


def test_xlsx_real_cell_coordinates_cannot_bypass_a_small_declared_dimension(monkeypatch) -> None:
    monkeypatch.setattr(parser, "MAX_DATASET_ROWS", 3)
    content = _xlsx('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:A1"/><sheetData><row r="1000"><c r="A1000"><v>1</v></c></row></sheetData></worksheet>')
    with pytest.raises(parser.DatasetParseError, match="rows|cell"):
        parser.parse_dataset_bytes(content, file_type="xlsx")


@pytest.mark.parametrize("false_directory_count", [False, True])
def test_xlsx_archive_member_count_is_bounded_before_zip_metadata_allocation(
    monkeypatch, false_directory_count: bool,
) -> None:
    monkeypatch.setattr(parser, "MAX_XLSX_ARCHIVE_MEMBERS", 2, raising=False)
    content = _xlsx('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    if false_directory_count:
        corrupted = bytearray(content)
        end_offset = corrupted.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", corrupted, end_offset + 8, 1, 1)
        content = bytes(corrupted)
    allocations = []
    original_zip_file = parser.zipfile.ZipFile

    def counted_zip_file(*args, **kwargs):
        allocations.append(True)
        return original_zip_file(*args, **kwargs)

    monkeypatch.setattr(parser.zipfile, "ZipFile", counted_zip_file)
    with pytest.raises(parser.DatasetParseError, match="archive|member"):
        parser.parse_dataset_bytes(content, file_type="xlsx")
    assert allocations == []


def test_unexpected_parser_errors_are_not_disguised_as_bad_input(monkeypatch) -> None:
    def broken_parser(content):
        raise RuntimeError("unexpected-parser-defect")

    monkeypatch.setattr(parser, "_parse_json", broken_parser)
    with pytest.raises(RuntimeError, match="unexpected-parser-defect"):
        parser.parse_dataset_bytes(b'[{"value":1}]', file_type="json")


def test_missing_xlsx_reader_is_an_explicit_unsupported_format(monkeypatch) -> None:
    import builtins

    original_import = builtins.__import__

    def without_reader(name, *args, **kwargs):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ImportError("Optional reader not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_reader)
    content = _xlsx('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    with pytest.raises(parser.DatasetParseError) as refused:
        parser.parse_dataset_bytes(content, file_type="xlsx")
    assert refused.value.status_code == 415
    assert refused.value.error_code == "dataset_format_unsupported"
    assert "openpyxl" in refused.value.detail