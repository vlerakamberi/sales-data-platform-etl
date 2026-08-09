from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sales_data_platform.ingestion.csv_reader import (
    ParsedCsvDocument,
    ParsedCsvRow,
    parse_csv,
)
from sales_data_platform.ingestion.errors import DiscoveryError, ParseError


def _write_csv(path: Path, content: str, *, newline: str = "") -> None:
    path.write_text(content, encoding="utf-8", newline=newline)


@pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
def test_normal_utf8_csv_parses_with_lf_or_crlf(
    tmp_path: Path, line_ending: str
) -> None:
    source = tmp_path / "orders.csv"
    _write_csv(
        source,
        line_ending.join(("order_number,sku", "O-1,SKU-1", "")),
        newline="",
    )

    document = parse_csv(source)

    assert document == ParsedCsvDocument(
        headers=("order_number", "sku"),
        rows=(ParsedCsvRow(row_number=2, values=("O-1", "SKU-1")),),
    )


def test_utf8_bom_is_removed_only_from_first_header(tmp_path: Path) -> None:
    source = tmp_path / "catalog.csv"
    source.write_bytes(b"\xef\xbb\xbfsku,product_name\nA-1,Widget\n")

    document = parse_csv(source)

    assert document.headers == ("sku", "product_name")
    assert document.rows[0].values == ("A-1", "Widget")


def test_invalid_utf8_raises_parse_error_without_fallback(tmp_path: Path) -> None:
    source = tmp_path / "invalid.csv"
    source.write_bytes(b"sku,name\nA-1,\x96\n")

    with pytest.raises(ParseError, match="valid UTF-8") as captured:
        parse_csv(source)

    assert captured.value.context["failure_category"] == "invalid_utf8"
    assert "A-1" not in str(captured.value)
    assert "A-1" not in repr(dict(captured.value.context))


def test_fixed_csv_dialect_supports_quotes_commas_and_double_quotes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "quoted.csv"
    _write_csv(source, 'sku,description\nA-1,"Large, ""blue"" widget"\n')

    document = parse_csv(source)

    assert document.rows[0].values == ("A-1", 'Large, "blue" widget')


def test_quoted_embedded_newline_preserves_starting_physical_row(
    tmp_path: Path,
) -> None:
    source = tmp_path / "multiline.csv"
    _write_csv(source, 'sku,description\nA-1,"first\nsecond"\nA-2,next\n')

    document = parse_csv(source)

    assert document.rows == (
        ParsedCsvRow(2, ("A-1", "first\nsecond")),
        ParsedCsvRow(4, ("A-2", "next")),
    )


def test_malformed_quoting_raises_parse_error(tmp_path: Path) -> None:
    source = tmp_path / "malformed.csv"
    _write_csv(source, 'sku,name\nA-1,"unclosed\n')

    with pytest.raises(ParseError, match="malformed syntax") as captured:
        parse_csv(source)

    assert captured.value.context == {
        "source_name": "malformed.csv",
        "failure_category": "malformed_csv",
    }
    assert "unclosed" not in str(captured.value)
    assert "unclosed" not in repr(dict(captured.value.context))


def test_first_non_blank_record_is_case_sensitive_ordered_header(
    tmp_path: Path,
) -> None:
    source = tmp_path / "headers.csv"
    _write_csv(source, "\n\r\nSKU,sku,Product_Name\nA-1,a-1,Widget\n")

    document = parse_csv(source)

    assert document.headers == ("SKU", "sku", "Product_Name")
    assert document.rows == (ParsedCsvRow(4, ("A-1", "a-1", "Widget")),)


@pytest.mark.parametrize("content", ["", "\n\r\n\n"])
def test_empty_or_blank_only_source_raises_parse_error(
    tmp_path: Path, content: str
) -> None:
    source = tmp_path / "empty.csv"
    _write_csv(source, content)

    with pytest.raises(ParseError, match="does not contain a header"):
        parse_csv(source)


def test_header_only_and_arbitrary_unknown_headers_are_accepted(tmp_path: Path) -> None:
    source = tmp_path / "arbitrary.csv"
    _write_csv(source, "foo,bar,baz\n")

    assert parse_csv(source) == ParsedCsvDocument(("foo", "bar", "baz"), ())


def test_exact_duplicate_headers_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.csv"
    _write_csv(source, "sku,sku\nA-1,A-2\n")

    with pytest.raises(ParseError, match="must be unique") as captured:
        parse_csv(source)

    assert captured.value.context["failure_category"] == "duplicate_header"


@pytest.mark.parametrize("header", ["sku,,price", 'sku,"",price'])
def test_empty_header_names_are_rejected(tmp_path: Path, header: str) -> None:
    source = tmp_path / "empty-header.csv"
    _write_csv(source, f"{header}\nA-1,,1.00\n")

    with pytest.raises(ParseError, match="must not be empty") as captured:
        parse_csv(source)

    assert captured.value.context["failure_category"] == "empty_header"


@pytest.mark.parametrize(
    ("data_row", "actual_width"),
    [("1,3", 2), ("1,2,3,4", 4)],
)
def test_row_width_mismatch_raises_parse_error_without_partial_result(
    tmp_path: Path, data_row: str, actual_width: int
) -> None:
    source = tmp_path / "wrong-width.csv"
    _write_csv(source, f"a,b,c\n0,0,0\n{data_row}\n")

    with pytest.raises(ParseError, match="field count") as captured:
        parse_csv(source)

    assert captured.value.context == {
        "source_name": "wrong-width.csv",
        "row_number": 3,
        "expected_field_count": 3,
        "actual_field_count": actual_width,
        "failure_category": "row_width",
    }
    assert data_row not in repr(dict(captured.value.context))


def test_explicit_empty_values_are_preserved_and_not_blank(tmp_path: Path) -> None:
    source = tmp_path / "empty-values.csv"
    _write_csv(source, "a,b,c\n1,,3\n,,\n")

    document = parse_csv(source)

    assert document.rows == (
        ParsedCsvRow(2, ("1", "", "3")),
        ParsedCsvRow(3, ("", "", "")),
    )


def test_blank_lines_are_ignored_but_affect_physical_row_numbers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "blank-lines.csv"
    _write_csv(source, "\n\na,b\n1,2\n\n3,4\n\n")

    document = parse_csv(source)

    assert document.headers == ("a", "b")
    assert document.rows == (
        ParsedCsvRow(4, ("1", "2")),
        ParsedCsvRow(6, ("3", "4")),
    )


def test_missing_source_raises_discovery_error(tmp_path: Path) -> None:
    source = tmp_path / "disappeared.csv"

    with pytest.raises(DiscoveryError, match="Unable to access") as captured:
        parse_csv(source)

    assert captured.value.context == {
        "source_name": "disappeared.csv",
        "failure_category": "source_access",
    }


def test_parser_representations_and_nested_collections_are_immutable() -> None:
    source_values = ["1", "2"]
    source_rows = [ParsedCsvRow(2, source_values)]  # type: ignore[arg-type]
    document = ParsedCsvDocument(["a", "b"], source_rows)  # type: ignore[arg-type]
    source_values[0] = "changed"
    source_rows.clear()

    assert document.headers == ("a", "b")
    assert document.rows == (ParsedCsvRow(2, ("1", "2")),)
    with pytest.raises(FrozenInstanceError):
        document.headers = ("changed",)  # type: ignore[misc]
    with pytest.raises(TypeError):
        document.rows[0] = ParsedCsvRow(3, ("3", "4"))  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        document.rows[0].row_number = 3  # type: ignore[misc]
    with pytest.raises(TypeError):
        document.rows[0].values[0] = "changed"  # type: ignore[index]
