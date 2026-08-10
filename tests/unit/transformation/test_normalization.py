"""Tests for deterministic transformation normalization helpers."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sales_data_platform.transformation.normalization import (
    normalize_business_identifier,
    normalize_text,
    normalize_timestamp_to_utc,
)


def test_identifier_strips_surrounding_whitespace_only() -> None:
    assert normalize_business_identifier("  Ab C-1  ") == "Ab C-1"


def test_identifier_preserves_internal_whitespace_and_case() -> None:
    assert normalize_business_identifier("Sku  MixedCase") == "Sku  MixedCase"


@pytest.mark.parametrize("value", ["", " ", "\t\r\n"])
def test_identifier_rejects_blank_result(value: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_business_identifier(value)


def test_text_normalization_is_deterministic_and_preserves_content() -> None:
    source = "  Product: Mixed-Case!  "

    assert normalize_text(source) == "Product: Mixed-Case!"
    assert normalize_text(source) == normalize_text(source)


def test_text_rejects_blank_result() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        normalize_text("   ")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            datetime(2026, 2, 3, 10, 30, tzinfo=timezone(timedelta(hours=3))),
            datetime(2026, 2, 3, 7, 30, tzinfo=UTC),
        ),
        (
            datetime(2026, 2, 3, 10, 30, tzinfo=timezone(-timedelta(hours=5))),
            datetime(2026, 2, 3, 15, 30, tzinfo=UTC),
        ),
    ],
)
def test_timestamp_normalizes_offsets_to_same_utc_instant(
    source: datetime, expected: datetime
) -> None:
    normalized = normalize_timestamp_to_utc(source)

    assert normalized == expected
    assert normalized.timestamp() == source.timestamp()
    assert source.tzinfo != UTC


def test_timestamp_rejects_naive_datetime_without_local_timezone_dependency() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        normalize_timestamp_to_utc(datetime(2026, 2, 3, 10, 30))
