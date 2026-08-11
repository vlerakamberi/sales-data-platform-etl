"""Integration validation for the local ingestion-to-transformation boundary."""

import logging
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import RunIdentity, ValidatedBatch
from sales_data_platform.ingestion.service import ingest_source_file
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    CustomerReferenceState,
    TransformationBatchResult,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.service import transform_batch

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "data" / "raw"
)
PRODUCT_KEY = SourceContractKey("northstar.product_catalog", 1)
ECOMMERCE_KEY = SourceContractKey("northstar.ecommerce_sales", 1)
RETAIL_KEY = SourceContractKey("northstar.retail_sales", 1)
PRIVATE_EMAIL = "private.customer@example.invalid"


def _settings(root: Path = FIXTURE_ROOT) -> Settings:
    return Settings(_env_file=None, INGESTION_SOURCE_ROOT=root)


def _ingest_and_transform(
    key: SourceContractKey,
    source: Path,
    *,
    settings: Settings | None = None,
    run_id: RunIdentity | None = None,
) -> tuple[ValidatedBatch, TransformationRuleSetKey, TransformationBatchResult]:
    batch = ingest_source_file(
        key, source, settings=settings or _settings(), run_id=run_id
    )
    ruleset = TransformationRuleSetKey(key, 1)
    result = transform_batch(batch, ruleset=ruleset)
    return batch, ruleset, result


def _assert_successful_boundary(
    batch: ValidatedBatch,
    ruleset: TransformationRuleSetKey,
    result: TransformationBatchResult,
) -> None:
    assert result.source_contract_key is batch.contract_key
    assert result.source_id is batch.source_id
    assert result.run_id is batch.run_id
    assert result.ruleset is ruleset
    assert result.record_count == batch.record_count == 2
    assert result.success_count == 2
    assert result.failure_count == 0
    assert len(result.successful_records) == 2
    assert tuple(outcome.provenance for outcome in result.outcomes) == tuple(
        record.provenance for record in batch.records
    )
    assert all(
        outcome.status is TransformationOutcomeStatus.SUCCESS
        for outcome in result.outcomes
    )


def test_product_catalog_ingestion_reaches_canonical_product_boundary() -> None:
    batch, ruleset, result = _ingest_and_transform(
        PRODUCT_KEY, FIXTURE_ROOT / "product_catalog" / "v1" / "products.csv"
    )

    _assert_successful_boundary(batch, ruleset, result)
    first, second = result.successful_records
    assert first == CanonicalProduct(
        sku="SKU-1001",
        product_name="Trail Bottle",
        category_code="OUTDOOR",
        list_price=Decimal("24.99"),
        unit_cost=Decimal("10.50"),
        product_currency_code="EUR",
        provenance=batch.records[0].provenance,
        ruleset=ruleset,
    )
    assert isinstance(second, CanonicalProduct)
    assert (second.sku, second.list_price, second.unit_cost) == ("SKU-1002", None, None)
    assert second.product_currency_code is None
    assert {field.name for field in fields(CanonicalProduct)}.isdisjoint(
        {"product_id", "product_category_id"}
    )


def test_ecommerce_boundary_preserves_lines_privacy_and_exact_arithmetic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(
        logging.INFO, logger="sales_data_platform.transformation.service"
    ):
        batch, ruleset, result = _ingest_and_transform(
            ECOMMERCE_KEY,
            FIXTURE_ROOT / "ecommerce_sales" / "v1" / "orders.csv",
        )

    _assert_successful_boundary(batch, ruleset, result)
    first, second = result.successful_records
    assert isinstance(first, CanonicalSalesLine)
    assert first.sales_channel_code == "ECOMMERCE"
    assert first.source_transaction_number == "WEB-1001"
    assert first.transaction_timestamp == datetime(2026, 8, 1, 8, 15, tzinfo=UTC)
    assert first.customer_reference_state is (
        CustomerReferenceState.UNRESOLVED_SOURCE_REFERENCE
    )
    assert first.product_sku == "SKU-1001"
    assert first.quantity == 2
    assert first.unit_price == Decimal("24.99")
    assert first.line_amount == Decimal("49.98")
    assert first.store_code is None
    assert second.source_transaction_number == "WEB-1002"
    assert second.customer_reference_state is CustomerReferenceState.ABSENT
    assert second.line_amount == Decimal("19.50")
    assert "customer1@example.invalid" not in caplog.text
    assert {field.name for field in fields(CanonicalSalesLine)}.isdisjoint(
        {"customer_id", "store_id", "product_id", "order_id"}
    )


def test_retail_boundary_preserves_business_and_source_local_references() -> None:
    batch, ruleset, result = _ingest_and_transform(
        RETAIL_KEY, FIXTURE_ROOT / "retail_sales" / "v1" / "sales.csv"
    )

    _assert_successful_boundary(batch, ruleset, result)
    first, second = result.successful_records
    assert isinstance(first, CanonicalSalesLine)
    assert first.sales_channel_code == "RETAIL"
    assert first.source_transaction_number == "POS-1001"
    assert first.store_code == "STORE-001"
    assert first.source_local_context == {"terminal_id": "TILL-01"}
    assert first.transaction_timestamp == datetime(2026, 8, 2, 7, 30, tzinfo=UTC)
    assert first.product_sku == "SKU-1001"
    assert (first.quantity, first.currency_code, first.line_amount) == (
        1,
        "EUR",
        Decimal("24.99"),
    )
    assert second.source_transaction_number == "POS-1002"
    assert second.source_local_context == {"terminal_id": "TILL-02"}
    assert second.line_amount == Decimal("39.00")


def test_physical_source_fractional_quantity_has_complete_ordered_accounting(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "ecommerce_sales" / "v1" / "orders.csv"
    source.parent.mkdir(parents=True)
    source.write_text(
        "order_number,order_timestamp,customer_email,sku,quantity,unit_price,"
        "currency_code\n"
        "WEB-1,2026-08-01T10:15:00+02:00,,SKU-1,2,10.125,EUR\n"
        f"WEB-2,2026-08-01T10:16:00+02:00,{PRIVATE_EMAIL},SKU-2,1.5,4.20,EUR\n"
        "WEB-3,2026-08-01T10:17:00+02:00,,SKU-3,3,2.10,EUR\n",
        encoding="utf-8",
        newline="",
    )

    with caplog.at_level(logging.INFO):
        batch, _, result = _ingest_and_transform(
            ECOMMERCE_KEY, source, settings=_settings(tmp_path)
        )

    assert tuple(record.provenance.row_number for record in batch.records) == (2, 3, 4)
    assert tuple(outcome.provenance.row_number for outcome in result.outcomes) == (
        2,
        3,
        4,
    )
    assert tuple(outcome.status for outcome in result.outcomes) == (
        TransformationOutcomeStatus.SUCCESS,
        TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
        TransformationOutcomeStatus.SUCCESS,
    )
    assert result.record_count == batch.record_count == 3
    assert result.success_count == 2
    assert result.failure_count == 1
    assert tuple(
        record.source_transaction_number for record in result.successful_records
    ) == ("WEB-1", "WEB-3")
    assert tuple(record.line_amount for record in result.successful_records) == (
        Decimal("20.250"),
        Decimal("6.30"),
    )
    assert PRIVATE_EMAIL not in caplog.text


def test_replay_is_deterministic_and_run_identity_only_changes_provenance() -> None:
    source = FIXTURE_ROOT / "ecommerce_sales" / "v1" / "orders.csv"
    first_run = RunIdentity(UUID("11111111-1111-1111-1111-111111111111"))
    second_run = RunIdentity(UUID("22222222-2222-2222-2222-222222222222"))
    first_batch, ruleset, first_result = _ingest_and_transform(
        ECOMMERCE_KEY, source, run_id=first_run
    )

    assert first_result == transform_batch(first_batch, ruleset=ruleset)

    _, _, second_result = _ingest_and_transform(
        ECOMMERCE_KEY, source, run_id=second_run
    )
    assert first_result.run_id != second_result.run_id
    assert first_result.source_id == second_result.source_id

    def business_values(
        result: TransformationBatchResult,
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                record.sales_channel_code,
                record.source_transaction_number,
                record.transaction_timestamp,
                record.store_code,
                record.customer_reference_state,
                record.product_sku,
                record.quantity,
                record.unit_price,
                record.currency_code,
                record.line_amount,
                record.source_local_context,
            )
            for record in result.successful_records
            if isinstance(record, CanonicalSalesLine)
        )

    assert business_values(first_result) == business_values(second_result)
    assert all(
        record.provenance.run_id is first_run
        for record in first_result.successful_records
    )
    assert all(
        record.provenance.run_id is second_run
        for record in second_result.successful_records
    )
