"""Tests for deterministic sales-channel seed definitions."""

from sales_data_platform.common.paths import SQL_SEED_DIR
from sales_data_platform.database.seed import (
    EXPECTED_SALES_CHANNELS,
    SALES_CHANNELS_SEED_PATH,
)


def test_sales_channel_seed_uses_centralized_path() -> None:
    assert SALES_CHANNELS_SEED_PATH == SQL_SEED_DIR / "sales_channels.sql"


def test_expected_sales_channels_are_exact_and_deterministic() -> None:
    assert EXPECTED_SALES_CHANNELS == (
        ("ECOMMERCE", "E-Commerce"),
        ("RETAIL", "Retail"),
    )


def test_seed_artifact_contains_only_approved_reference_rows() -> None:
    sql = SALES_CHANNELS_SEED_PATH.read_text(encoding="utf-8")

    assert "('ECOMMERCE', 'E-Commerce')" in sql
    assert "('RETAIL', 'Retail')" in sql
    assert sql.count("('") == 2
    assert "DO UPDATE" not in sql
