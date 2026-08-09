"""Deterministic structural parsing for physical CSV source files."""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sales_data_platform.ingestion.errors import DiscoveryError, ParseError


@dataclass(frozen=True, slots=True)
class ParsedCsvRow:
    """One immutable logical CSV row and its physical starting line."""

    row_number: int
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True, slots=True)
class ParsedCsvDocument:
    """An immutable structurally parsed CSV document."""

    headers: tuple[str, ...]
    rows: tuple[ParsedCsvRow, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", tuple(self.headers))
        object.__setattr__(self, "rows", tuple(self.rows))


def _parse_open_csv(source: TextIO, source_name: str) -> ParsedCsvDocument:
    reader = csv.reader(
        source,
        delimiter=",",
        quotechar='"',
        doublequote=True,
        escapechar=None,
        skipinitialspace=False,
        strict=True,
    )
    headers: tuple[str, ...] | None = None
    parsed_rows: list[ParsedCsvRow] = []

    while True:
        starting_line = reader.line_num + 1
        try:
            fields = next(reader)
        except StopIteration:
            break

        if not fields:
            continue
        values = tuple(fields)
        if headers is None:
            if any(header == "" for header in values):
                raise ParseError(
                    "CSV header names must not be empty",
                    context={
                        "source_name": source_name,
                        "row_number": starting_line,
                        "failure_category": "empty_header",
                    },
                )
            if len(values) != len(set(values)):
                raise ParseError(
                    "CSV header names must be unique",
                    context={
                        "source_name": source_name,
                        "row_number": starting_line,
                        "failure_category": "duplicate_header",
                    },
                )
            headers = values
            continue

        if len(values) != len(headers):
            raise ParseError(
                "CSV row field count does not match the header",
                context={
                    "source_name": source_name,
                    "row_number": starting_line,
                    "expected_field_count": len(headers),
                    "actual_field_count": len(values),
                    "failure_category": "row_width",
                },
            )
        parsed_rows.append(ParsedCsvRow(starting_line, values))

    if headers is None:
        raise ParseError(
            "CSV source does not contain a header",
            context={
                "source_name": source_name,
                "failure_category": "missing_header",
            },
        )
    return ParsedCsvDocument(headers, tuple(parsed_rows))


def parse_csv(path: Path) -> ParsedCsvDocument:
    """Parse one UTF-8 CSV file using the fixed ingestion dialect."""

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            return _parse_open_csv(source, path.name)
    except UnicodeDecodeError as error:
        raise ParseError(
            "CSV source is not valid UTF-8",
            context={
                "source_name": path.name,
                "failure_category": "invalid_utf8",
            },
        ) from error
    except csv.Error as error:
        raise ParseError(
            "CSV source has malformed syntax",
            context={
                "source_name": path.name,
                "failure_category": "malformed_csv",
            },
        ) from error
    except OSError as error:
        raise DiscoveryError(
            "Unable to access CSV source",
            context={
                "source_name": path.name,
                "failure_category": "source_access",
            },
        ) from error
