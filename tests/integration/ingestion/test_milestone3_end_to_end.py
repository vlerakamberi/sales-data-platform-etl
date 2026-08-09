import hashlib
import logging
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.errors import (
    DiscoveryError,
    ParseError,
    RecordValidationError,
    SourceContractError,
)
from sales_data_platform.ingestion.models import ContentSha256, ValidatedBatch
from sales_data_platform.ingestion.service import ingest_source_file

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "data" / "raw"
)
PRODUCT_KEY = SourceContractKey("northstar.product_catalog", 1)
ECOMMERCE_KEY = SourceContractKey("northstar.ecommerce_sales", 1)
RETAIL_KEY = SourceContractKey("northstar.retail_sales", 1)
FIXTURE_EMAIL = "customer1@example.invalid"


def _settings(root: Path = FIXTURE_ROOT) -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=root)


def _assert_batch_provenance(
    batch: ValidatedBatch, key: SourceContractKey, identifier: str
) -> None:
    assert type(batch) is ValidatedBatch
    assert batch.contract_key == key
    assert batch.record_count == 2
    assert [record.provenance.row_number for record in batch.records] == [2, 3]
    for record in batch.records:
        assert record.provenance.contract_key == key
        assert record.provenance.source_identifier == identifier
        assert record.provenance.source_id == batch.source_id
        assert record.provenance.run_id == batch.run_id


def _ecommerce_source(root: Path, content: str) -> Path:
    source = root / "ecommerce_sales" / "v1" / "orders.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8", newline="")
    return source


def test_product_catalog_fixture_reaches_validated_boundary() -> None:
    source = FIXTURE_ROOT / "product_catalog" / "v1" / "products.csv"

    batch = ingest_source_file(PRODUCT_KEY, source, settings=_settings())

    _assert_batch_provenance(batch, PRODUCT_KEY, "product_catalog/v1/products.csv")
    assert batch.records[0].values == {
        "sku": "SKU-1001",
        "product_name": "Trail Bottle",
        "category_code": "OUTDOOR",
        "list_price": Decimal("24.99"),
        "unit_cost": Decimal("10.50"),
        "currency_code": "EUR",
    }
    assert batch.records[1].values["list_price"] is None
    assert batch.records[1].values["unit_cost"] is None
    assert batch.records[1].values["currency_code"] is None


def test_ecommerce_fixture_preserves_types_offsets_and_safe_lifecycle_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = FIXTURE_ROOT / "ecommerce_sales" / "v1" / "orders.csv"

    with caplog.at_level(logging.INFO):
        batch = ingest_source_file(ECOMMERCE_KEY, source, settings=_settings())

    _assert_batch_provenance(batch, ECOMMERCE_KEY, "ecommerce_sales/v1/orders.csv")
    first, second = batch.records
    assert first.values["quantity"] == Decimal("2")
    assert first.values["unit_price"] == Decimal("24.99")
    assert first.values["order_timestamp"].utcoffset() == timedelta(hours=2)
    assert second.values["order_timestamp"].utcoffset() == timedelta(0)
    assert second.values["customer_email"] is None
    for event in (
        "Ingestion started",
        "Source selected",
        "Source identity established",
        "Parsing completed",
        "Validation completed",
        "Ingestion succeeded",
    ):
        assert event in caplog.text
    assert FIXTURE_EMAIL not in caplog.text
    assert "WEB-1001" not in caplog.text


def test_retail_fixture_preserves_source_specific_fields() -> None:
    source = FIXTURE_ROOT / "retail_sales" / "v1" / "sales.csv"

    batch = ingest_source_file(RETAIL_KEY, source, settings=_settings())

    _assert_batch_provenance(batch, RETAIL_KEY, "retail_sales/v1/sales.csv")
    assert [record.values["terminal_id"] for record in batch.records] == [
        "TILL-01",
        "TILL-02",
    ]
    assert batch.records[0].values["transaction_timestamp"].utcoffset() == timedelta(
        hours=2
    )
    assert not hasattr(batch, "database")
    assert not hasattr(batch.records[0], "canonical_values")


def test_fixture_replay_is_content_stable_but_run_distinct() -> None:
    source = FIXTURE_ROOT / "ecommerce_sales" / "v1" / "orders.csv"

    first = ingest_source_file(ECOMMERCE_KEY, source, settings=_settings())
    second = ingest_source_file(ECOMMERCE_KEY, source, settings=_settings())

    expected_hash = ContentSha256(hashlib.sha256(source.read_bytes()).hexdigest())
    assert first.records[0].provenance.content_sha256 == expected_hash
    assert first.source_id == second.source_id
    assert first.records[0].provenance.content_sha256 == (
        second.records[0].provenance.content_sha256
    )
    assert tuple(record.values for record in first.records) == tuple(
        record.values for record in second.records
    )
    assert first.run_id != second.run_id


def test_unknown_contract_fails_without_a_batch(tmp_path: Path) -> None:
    with pytest.raises(SourceContractError):
        ingest_source_file(
            SourceContractKey("northstar.unknown", 1),
            tmp_path / "orders.csv",
            settings=_settings(tmp_path),
        )


def test_noneligible_path_fails_without_a_batch(tmp_path: Path) -> None:
    outside = tmp_path / "orders.csv"
    outside.write_text("not,eligible\n", encoding="utf-8")

    with pytest.raises(DiscoveryError):
        ingest_source_file(ECOMMERCE_KEY, outside, settings=_settings(tmp_path))


def test_malformed_csv_fails_without_a_batch(tmp_path: Path) -> None:
    source = _ecommerce_source(
        tmp_path,
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        'WEB-1,"unclosed\n',
    )

    with pytest.raises(ParseError):
        ingest_source_file(ECOMMERCE_KEY, source, settings=_settings(tmp_path))


def test_invalid_later_record_rejects_the_whole_file_and_logs_safely(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _ecommerce_source(
        tmp_path,
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        f"WEB-1,2026-08-01T10:15:00+02:00,{FIXTURE_EMAIL},SKU-1,1,24.99,EUR\n"
        "WEB-2,2026-08-01T10:16:00+02:00,,SKU-2,0,19.50,EUR\n",
    )
    batch = None

    with caplog.at_level(logging.INFO), pytest.raises(RecordValidationError):
        batch = ingest_source_file(ECOMMERCE_KEY, source, settings=_settings(tmp_path))

    assert batch is None
    assert "Ingestion failed" in caplog.text
    assert FIXTURE_EMAIL not in caplog.text
    assert "WEB-1" not in caplog.text
    assert "WEB-2" not in caplog.text
