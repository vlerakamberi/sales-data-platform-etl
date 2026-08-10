"""Explicit mappings from validated v1 sources to canonical records."""

from collections.abc import Callable, Mapping
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import ValidatedRecord
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalRecord,
    CanonicalSalesLine,
    CustomerReferenceState,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.normalization import (
    normalize_business_identifier,
    normalize_text,
    normalize_timestamp_to_utc,
)
from sales_data_platform.transformation.rules import (
    derive_line_amount,
    require_integral_quantity,
    require_product_monetary_consistency,
)

PRODUCT_CATALOG_V1 = SourceContractKey("northstar.product_catalog", 1)
ECOMMERCE_SALES_V1 = SourceContractKey("northstar.ecommerce_sales", 1)
RETAIL_SALES_V1 = SourceContractKey("northstar.retail_sales", 1)


class TransformationMappingError(ValueError):
    """A controlled failure at the exact source-to-canonical mapping boundary."""


class UnsupportedSourceContractError(TransformationMappingError):
    """The supplied source contract has no exact approved mapper."""


def _require_mapping_identity(
    record: ValidatedRecord,
    ruleset: TransformationRuleSetKey,
    expected_contract: SourceContractKey,
) -> None:
    if record.provenance.contract_key != expected_contract:
        raise TransformationMappingError(
            "Validated record does not match the mapper source contract"
        )
    if ruleset.source_contract_key != expected_contract:
        raise TransformationMappingError(
            "Transformation ruleset does not match the mapper source contract"
        )


def map_product_catalog_v1(
    record: ValidatedRecord, ruleset: TransformationRuleSetKey
) -> CanonicalProduct:
    """Map one validated product-catalog v1 record."""

    _require_mapping_identity(record, ruleset, PRODUCT_CATALOG_V1)
    values = record.values
    list_price = cast(Decimal | None, values["list_price"])
    unit_cost = cast(Decimal | None, values["unit_cost"])
    currency_code = cast(str | None, values["currency_code"])
    require_product_monetary_consistency(list_price, unit_cost, currency_code)

    return CanonicalProduct(
        sku=normalize_business_identifier(cast(str, values["sku"])),
        product_name=normalize_text(cast(str, values["product_name"])),
        category_code=normalize_business_identifier(cast(str, values["category_code"])),
        list_price=list_price,
        unit_cost=unit_cost,
        product_currency_code=currency_code,
        provenance=record.provenance,
        ruleset=ruleset,
    )


def map_ecommerce_sales_v1(
    record: ValidatedRecord, ruleset: TransformationRuleSetKey
) -> CanonicalSalesLine:
    """Map one validated e-commerce-sales v1 record."""

    _require_mapping_identity(record, ruleset, ECOMMERCE_SALES_V1)
    values = record.values
    quantity = require_integral_quantity(cast(Decimal, values["quantity"]))
    unit_price = cast(Decimal, values["unit_price"])
    customer_reference_state = (
        CustomerReferenceState.ABSENT
        if values["customer_email"] is None
        else CustomerReferenceState.UNRESOLVED_SOURCE_REFERENCE
    )

    return CanonicalSalesLine(
        sales_channel_code="ECOMMERCE",
        source_transaction_number=normalize_business_identifier(
            cast(str, values["order_number"])
        ),
        transaction_timestamp=normalize_timestamp_to_utc(
            cast(datetime, values["order_timestamp"])
        ),
        store_code=None,
        customer_reference_state=customer_reference_state,
        product_sku=normalize_business_identifier(cast(str, values["sku"])),
        quantity=quantity,
        unit_price=unit_price,
        currency_code=cast(str, values["currency_code"]),
        line_amount=derive_line_amount(quantity, unit_price),
        source_local_context={},
        provenance=record.provenance,
        ruleset=ruleset,
    )


def map_retail_sales_v1(
    record: ValidatedRecord, ruleset: TransformationRuleSetKey
) -> CanonicalSalesLine:
    """Map one validated retail-sales v1 record."""

    _require_mapping_identity(record, ruleset, RETAIL_SALES_V1)
    values = record.values
    quantity = require_integral_quantity(cast(Decimal, values["quantity"]))
    unit_price = cast(Decimal, values["unit_price"])

    return CanonicalSalesLine(
        sales_channel_code="RETAIL",
        source_transaction_number=normalize_business_identifier(
            cast(str, values["receipt_number"])
        ),
        transaction_timestamp=normalize_timestamp_to_utc(
            cast(datetime, values["transaction_timestamp"])
        ),
        store_code=normalize_business_identifier(cast(str, values["store_code"])),
        customer_reference_state=CustomerReferenceState.ABSENT,
        product_sku=normalize_business_identifier(cast(str, values["sku"])),
        quantity=quantity,
        unit_price=unit_price,
        currency_code=cast(str, values["currency_code"]),
        line_amount=derive_line_amount(quantity, unit_price),
        source_local_context={"terminal_id": values["terminal_id"]},
        provenance=record.provenance,
        ruleset=ruleset,
    )


type _Mapper = Callable[[ValidatedRecord, TransformationRuleSetKey], CanonicalRecord]

_MAPPERS: Mapping[SourceContractKey, _Mapper] = MappingProxyType(
    {
        PRODUCT_CATALOG_V1: map_product_catalog_v1,
        ECOMMERCE_SALES_V1: map_ecommerce_sales_v1,
        RETAIL_SALES_V1: map_retail_sales_v1,
    }
)


def map_validated_record(
    source_contract_key: SourceContractKey,
    record: ValidatedRecord,
    ruleset: TransformationRuleSetKey,
) -> CanonicalRecord:
    """Dispatch one validated record by exact supported source-contract identity."""

    mapper = _MAPPERS.get(source_contract_key)
    if mapper is None:
        raise UnsupportedSourceContractError(
            "Unsupported source contract for canonical transformation"
        )
    return mapper(record, ruleset)
