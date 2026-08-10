"""Tests for exact source-contract-specific canonical mappings."""

from dataclasses import fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
    ValidatedRecord,
)
from sales_data_platform.transformation.mapping import (
    ECOMMERCE_SALES_V1,
    PRODUCT_CATALOG_V1,
    RETAIL_SALES_V1,
    TransformationMappingError,
    UnsupportedSourceContractError,
    map_ecommerce_sales_v1,
    map_product_catalog_v1,
    map_retail_sales_v1,
    map_validated_record,
)
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    CustomerReferenceState,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.rules import TransformationRuleViolation


def _provenance(contract_key: SourceContractKey) -> RecordProvenance:
    return RecordProvenance(
        contract_key=contract_key,
        source_identifier="governed/v1/source.csv",
        content_sha256=ContentSha256("b" * 64),
        source_id=SourceIdentity("source-identity"),
        run_id=RunIdentity(UUID("12345678-1234-5678-1234-567812345678")),
        row_number=2,
    )


def _record(
    contract_key: SourceContractKey, values: dict[str, object]
) -> ValidatedRecord:
    return ValidatedRecord(values, _provenance(contract_key))


def _ruleset(contract_key: SourceContractKey) -> TransformationRuleSetKey:
    return TransformationRuleSetKey(contract_key, 1)


def _product_record(
    *,
    list_price: Decimal | None = Decimal("19.990"),
    unit_cost: Decimal | None = Decimal("7.125"),
    currency_code: str | None = "USD",
) -> ValidatedRecord:
    return _record(
        PRODUCT_CATALOG_V1,
        {
            "sku": "  Sku Mixed  ",
            "product_name": "  Northstar Product  ",
            "category_code": "  Category Mixed  ",
            "list_price": list_price,
            "unit_cost": unit_cost,
            "currency_code": currency_code,
        },
    )


def _ecommerce_record(
    *, customer_email: str | None = None, quantity: Decimal = Decimal("2.0")
) -> ValidatedRecord:
    return _record(
        ECOMMERCE_SALES_V1,
        {
            "order_number": "  Order Mixed  ",
            "order_timestamp": datetime(
                2026, 4, 5, 15, 30, tzinfo=timezone(timedelta(hours=3))
            ),
            "customer_email": customer_email,
            "sku": "  Sku Mixed  ",
            "quantity": quantity,
            "unit_price": Decimal("3.1250"),
            "currency_code": "EUR",
        },
    )


def _retail_record() -> ValidatedRecord:
    return _record(
        RETAIL_SALES_V1,
        {
            "receipt_number": "  Receipt Mixed  ",
            "transaction_timestamp": datetime(
                2026, 4, 5, 9, 15, tzinfo=timezone(-timedelta(hours=4))
            ),
            "store_code": "  Store Mixed  ",
            "terminal_id": "Terminal-07",
            "sku": "  Retail Sku  ",
            "quantity": Decimal("3.000"),
            "unit_price": Decimal("2.345"),
            "currency_code": "USD",
        },
    )


def test_product_catalog_v1_maps_exact_values_and_identity() -> None:
    record = _product_record()
    ruleset = _ruleset(PRODUCT_CATALOG_V1)

    product = map_product_catalog_v1(record, ruleset)

    assert product == CanonicalProduct(
        sku="Sku Mixed",
        product_name="Northstar Product",
        category_code="Category Mixed",
        list_price=Decimal("19.990"),
        unit_cost=Decimal("7.125"),
        product_currency_code="USD",
        provenance=record.provenance,
        ruleset=ruleset,
    )
    assert product.provenance is record.provenance
    assert product.ruleset is ruleset


@pytest.mark.parametrize(
    ("list_price", "unit_cost", "currency_code"),
    [
        (None, None, "USD"),
        (Decimal("1.00"), None, None),
        (None, Decimal("1.00"), None),
    ],
)
def test_product_mapping_enforces_monetary_consistency(
    list_price: Decimal | None,
    unit_cost: Decimal | None,
    currency_code: str | None,
) -> None:
    with pytest.raises(TransformationRuleViolation, match="currency"):
        map_product_catalog_v1(
            _product_record(
                list_price=list_price,
                unit_cost=unit_cost,
                currency_code=currency_code,
            ),
            _ruleset(PRODUCT_CATALOG_V1),
        )


@pytest.mark.parametrize(
    ("customer_email", "expected_state"),
    [
        (None, CustomerReferenceState.ABSENT),
        ("customer@example.com", CustomerReferenceState.UNRESOLVED_SOURCE_REFERENCE),
    ],
)
def test_ecommerce_v1_maps_customer_state_without_customer_identity(
    customer_email: str | None, expected_state: CustomerReferenceState
) -> None:
    record = _ecommerce_record(customer_email=customer_email)
    ruleset = _ruleset(ECOMMERCE_SALES_V1)

    line = map_ecommerce_sales_v1(record, ruleset)

    assert line.sales_channel_code == "ECOMMERCE"
    assert line.source_transaction_number == "Order Mixed"
    assert line.store_code is None
    assert line.customer_reference_state is expected_state
    assert line.product_sku == "Sku Mixed"
    assert line.transaction_timestamp == datetime(2026, 4, 5, 12, 30, tzinfo=UTC)
    assert line.quantity == 2
    assert line.unit_price is record.values["unit_price"]
    assert line.line_amount == Decimal("6.2500")
    assert line.currency_code == "EUR"
    assert line.source_local_context == {}
    assert line.provenance is record.provenance
    assert line.ruleset is ruleset
    assert "customer_email" not in {field.name for field in fields(line)}


def test_retail_v1_maps_store_terminal_and_exact_amount() -> None:
    record = _retail_record()
    ruleset = _ruleset(RETAIL_SALES_V1)

    line = map_retail_sales_v1(record, ruleset)

    assert line.sales_channel_code == "RETAIL"
    assert line.source_transaction_number == "Receipt Mixed"
    assert line.store_code == "Store Mixed"
    assert line.product_sku == "Retail Sku"
    assert line.transaction_timestamp == datetime(2026, 4, 5, 13, 15, tzinfo=UTC)
    assert line.customer_reference_state is CustomerReferenceState.ABSENT
    assert line.quantity == 3
    assert line.unit_price is record.values["unit_price"]
    assert line.line_amount == Decimal("7.035")
    assert line.source_local_context == {"terminal_id": "Terminal-07"}
    assert line.provenance is record.provenance
    assert line.ruleset is ruleset


@pytest.mark.parametrize(
    ("contract_key", "record_factory", "expected_type"),
    [
        (PRODUCT_CATALOG_V1, _product_record, CanonicalProduct),
        (ECOMMERCE_SALES_V1, _ecommerce_record, CanonicalSalesLine),
        (RETAIL_SALES_V1, _retail_record, CanonicalSalesLine),
    ],
)
def test_dispatches_only_exact_supported_contracts(
    contract_key: SourceContractKey,
    record_factory: object,
    expected_type: type[CanonicalProduct] | type[CanonicalSalesLine],
) -> None:
    record = record_factory()  # type: ignore[operator]

    result = map_validated_record(contract_key, record, _ruleset(contract_key))

    assert isinstance(result, expected_type)


@pytest.mark.parametrize(
    "unsupported_key",
    [
        SourceContractKey("northstar.product_catalog", 2),
        SourceContractKey("northstar.unknown", 1),
    ],
)
def test_unsupported_contract_or_version_fails_explicitly(
    unsupported_key: SourceContractKey,
) -> None:
    with pytest.raises(UnsupportedSourceContractError, match="Unsupported"):
        map_validated_record(
            unsupported_key,
            _product_record(),
            TransformationRuleSetKey(unsupported_key, 1),
        )


def test_mapper_rejects_record_or_ruleset_for_another_contract() -> None:
    with pytest.raises(TransformationMappingError, match="record"):
        map_product_catalog_v1(_ecommerce_record(), _ruleset(PRODUCT_CATALOG_V1))
    with pytest.raises(TransformationMappingError, match="ruleset"):
        map_product_catalog_v1(_product_record(), _ruleset(ECOMMERCE_SALES_V1))


def test_fractional_quantity_is_rejected_without_rounding() -> None:
    with pytest.raises(TransformationRuleViolation, match="exact integer"):
        map_ecommerce_sales_v1(
            _ecommerce_record(quantity=Decimal("1.5")),
            _ruleset(ECOMMERCE_SALES_V1),
        )


def test_canonical_sales_line_has_no_surrogate_identity_fields() -> None:
    field_names = {field.name for field in fields(CanonicalSalesLine)}

    assert field_names.isdisjoint(
        {
            "customer_id",
            "store_id",
            "product_id",
            "order_id",
            "order_item_id",
            "sales_channel_id",
        }
    )


def test_canonical_product_has_no_surrogate_identity_fields() -> None:
    field_names = {field.name for field in fields(CanonicalProduct)}

    assert field_names.isdisjoint({"product_id", "product_category_id"})


@pytest.mark.parametrize(
    ("contract_key", "record"),
    [
        (PRODUCT_CATALOG_V1, _product_record()),
        (ECOMMERCE_SALES_V1, _ecommerce_record(customer_email="a@example.com")),
        (RETAIL_SALES_V1, _retail_record()),
    ],
)
def test_repeated_mapping_is_deterministic(
    contract_key: SourceContractKey, record: ValidatedRecord
) -> None:
    ruleset = _ruleset(contract_key)

    first = map_validated_record(contract_key, record, ruleset)
    second = map_validated_record(contract_key, record, ruleset)

    assert first == second
