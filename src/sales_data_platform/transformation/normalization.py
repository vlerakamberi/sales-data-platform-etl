"""Small deterministic normalization helpers for canonical transformation."""

from datetime import UTC, datetime


def normalize_business_identifier(value: str) -> str:
    """Strip surrounding whitespace while preserving case and internal content."""

    return _normalize_non_blank_text(value, label="Business identifier")


def normalize_text(value: str) -> str:
    """Strip surrounding whitespace from canonical text without other cleanup."""

    return _normalize_non_blank_text(value, label="Text")


def _normalize_non_blank_text(value: str, *, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    return normalized


def normalize_timestamp_to_utc(value: datetime) -> datetime:
    """Convert a timezone-aware datetime to UTC while preserving its instant."""

    if not isinstance(value, datetime):
        raise TypeError("Timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(UTC)
