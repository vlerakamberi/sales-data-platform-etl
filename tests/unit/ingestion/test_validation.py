from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import (
    BUILT_IN_REGISTRY,
    SourceContract,
    SourceContractKey,
)
from sales_data_platform.ingestion.csv_reader import ParsedCsvDocument, ParsedCsvRow
from sales_data_platform.ingestion.errors import RecordValidationError
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RunIdentity,
    SourceIdentity,
    ValidatedBatch,
    ValidatedRecord,
)
from sales_data_platform.ingestion.validation import (
    ValidationProvenance,
    validate_document,
)

CONTENT_SHA256 = ContentSha256("a" * 64)
SOURCE_ID = SourceIdentity("deterministic-source-id")
RUN_ID = RunIdentity(UUID("12345678-1234-5678-1234-567812345678"))

VALID_ROWS = {
    "northstar.product_catalog": (
        "SKU-1",
        "Widget",
        "CAT-1",
        "10.50",
        "4.25",
        "EUR",
    ),
    "northstar.ecommerce_sales": (
        "ORDER-1",
        "2026-08-09T20:30:00+02:00",
        "customer@example.com",
        "SKU-1",
        "2",
        "10.50",
        "USD",
    ),
    "northstar.retail_sales": (
        "RECEIPT-1",
        "2026-08-09T13:30:00-05:00",
        "STORE-1",
        " Terminal 01 ",
        "SKU-1",
        "1",
        "9.99",
        "EUR",
    ),
}


def _contract(contract_id: str) -> SourceContract:
    return BUILT_IN_REGISTRY.resolve(contract_id, 1)


def _provenance(
    contract: SourceContract, *, contract_key: SourceContractKey | None = None
) -> ValidationProvenance:
    return ValidationProvenance(
        contract_key=contract_key or contract.key,
        source_identifier=f"{contract.key.source_contract_id}/v1/source.csv",
        content_sha256=CONTENT_SHA256,
        source_id=SOURCE_ID,
        run_id=RUN_ID,
    )


def _document(
    contract: SourceContract,
    values: tuple[str, ...] | None = None,
    *,
    headers: tuple[str, ...] | None = None,
    row_number: int = 2,
) -> ParsedCsvDocument:
    return ParsedCsvDocument(
        headers or tuple(field.name for field in contract.fields),
        (
            ParsedCsvRow(
                row_number, values or VALID_ROWS[contract.key.source_contract_id]
            ),
        ),
    )


@pytest.mark.parametrize("contract_id", tuple(VALID_ROWS))
def test_exact_contract_headers_and_valid_records_succeed(contract_id: str) -> None:
    contract = _contract(contract_id)
    records = validate_document(contract, _document(contract), _provenance(contract))

    assert len(records) == 1
    assert type(records[0]) is ValidatedRecord
    assert not isinstance(records, ValidatedBatch)


def test_reordered_headers_map_values_by_source_field_name() -> None:
    contract = _contract("northstar.product_catalog")
    headers = (
        "currency_code",
        "sku",
        "unit_cost",
        "category_code",
        "list_price",
        "product_name",
    )
    values = ("EUR", "SKU-1", "4.25", "CAT-1", "10.50", "Widget")

    record = validate_document(
        contract,
        _document(contract, values, headers=headers, row_number=8),
        _provenance(contract),
    )[0]

    assert record.values == {
        "sku": "SKU-1",
        "product_name": "Widget",
        "category_code": "CAT-1",
        "list_price": Decimal("10.50"),
        "unit_cost": Decimal("4.25"),
        "currency_code": "EUR",
    }
    assert record.provenance.row_number == 8
    assert record.provenance.source_id is SOURCE_ID
    assert record.provenance.run_id is RUN_ID
    assert record.provenance.content_sha256 is CONTENT_SHA256


@pytest.mark.parametrize(
    ("headers", "missing", "unexpected"),
    [
        (
            ("sku", "product_name", "category_code", "list_price", "unit_cost"),
            ("currency_code",),
            (),
        ),
        (
            (
                "sku",
                "product_name",
                "category_code",
                "list_price",
                "unit_cost",
                "extra",
            ),
            ("currency_code",),
            ("extra",),
        ),
        (
            (
                "SKU",
                "product_name",
                "category_code",
                "list_price",
                "unit_cost",
                "currency_code",
            ),
            ("sku",),
            ("SKU",),
        ),
    ],
)
def test_header_mismatch_is_rejected(
    headers: tuple[str, ...], missing: tuple[str, ...], unexpected: tuple[str, ...]
) -> None:
    contract = _contract("northstar.product_catalog")
    document = ParsedCsvDocument(headers, ())

    with pytest.raises(RecordValidationError, match="headers") as captured:
        validate_document(contract, document, _provenance(contract))

    assert captured.value.context["missing_headers"] == missing
    assert captured.value.context["unexpected_headers"] == unexpected


def test_nullable_empty_values_become_none() -> None:
    contract = _contract("northstar.product_catalog")
    record = validate_document(
        contract,
        _document(contract, ("SKU-1", "Widget", "CAT-1", "", "", "")),
        _provenance(contract),
    )[0]

    assert record.values["list_price"] is None
    assert record.values["unit_cost"] is None
    assert record.values["currency_code"] is None


def test_empty_nullable_customer_email_becomes_none() -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[2] = ""

    record = validate_document(
        contract, _document(contract, tuple(values)), _provenance(contract)
    )[0]

    assert record.values["customer_email"] is None


def test_empty_non_nullable_field_is_rejected_with_safe_context() -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[0] = ""

    with pytest.raises(RecordValidationError, match="Non-nullable") as captured:
        validate_document(
            contract,
            _document(contract, tuple(values), row_number=17),
            _provenance(contract),
        )

    assert captured.value.context["field_name"] == "order_number"
    assert captured.value.context["row_number"] == 17
    assert "customer@example.com" not in str(captured.value)
    assert "customer@example.com" not in repr(dict(captured.value.context))


def test_string_values_preserve_case_and_whitespace_exactly() -> None:
    contract = _contract("northstar.product_catalog")
    record = validate_document(
        contract,
        _document(contract, (" AbC ", "   ", "CaT", "", "", "")),
        _provenance(contract),
    )[0]

    assert record.values["sku"] == " AbC "
    assert record.values["product_name"] == "   "
    assert record.values["category_code"] == "CaT"


@pytest.mark.parametrize(
    ("source_value", "expected"),
    [
        ("1", Decimal("1")),
        ("10.50", Decimal("10.50")),
        ("0", Decimal("0")),
        ("1E+2", Decimal("1E+2")),
    ],
)
def test_valid_non_negative_decimal_forms_are_accepted(
    source_value: str, expected: Decimal
) -> None:
    contract = _contract("northstar.product_catalog")
    values = ("SKU-1", "Widget", "CAT-1", source_value, "0", "EUR")

    record = validate_document(
        contract, _document(contract, values), _provenance(contract)
    )[0]

    assert record.values["list_price"] == expected


@pytest.mark.parametrize(
    "source_value",
    ["bad", " 1", "1 ", "1,5", "1_000", "NaN", "-NaN", "Infinity", "Inf"],
)
def test_invalid_or_non_finite_decimal_forms_are_rejected(source_value: str) -> None:
    contract = _contract("northstar.product_catalog")
    values = ("SKU-1", "Widget", "CAT-1", source_value, "0", "EUR")

    with pytest.raises(RecordValidationError, match="decimal") as captured:
        validate_document(contract, _document(contract, values), _provenance(contract))

    assert captured.value.context["field_name"] == "list_price"
    assert source_value not in captured.value.context.values()


@pytest.mark.parametrize(("field_index", "source_value"), [(3, "-0.01"), (4, "-1")])
def test_negative_product_costs_are_rejected(
    field_index: int, source_value: str
) -> None:
    contract = _contract("northstar.product_catalog")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[field_index] = source_value

    with pytest.raises(RecordValidationError, match="constraint"):
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )


@pytest.mark.parametrize("quantity", ["0", "-1"])
def test_sales_quantity_must_be_positive(quantity: str) -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[4] = quantity

    with pytest.raises(RecordValidationError) as captured:
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )

    assert captured.value.context["failure_category"] == "positive"


def test_zero_unit_price_is_non_negative_and_accepted() -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[5] = "0"
    record = validate_document(
        contract, _document(contract, tuple(values)), _provenance(contract)
    )[0]
    assert record.values["unit_price"] == Decimal("0")


def test_negative_ecommerce_unit_price_is_rejected() -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[5] = "-0.01"

    with pytest.raises(RecordValidationError) as captured:
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )

    assert captured.value.context["failure_category"] == "non_negative"


@pytest.mark.parametrize(
    ("source_value", "offset"),
    [
        ("2026-08-09T18:30:00Z", timedelta(0)),
        ("2026-08-09T18:30:00+00:00", timedelta(0)),
        ("2026-08-09T20:30:00+02:00", timedelta(hours=2)),
        ("2026-08-09T13:30:00-05:00", -timedelta(hours=5)),
        ("2026-08-09T18:30:00.123+02:00", timedelta(hours=2)),
    ],
)
def test_timezone_aware_iso_timestamps_preserve_source_offset(
    source_value: str, offset: timedelta
) -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[1] = source_value

    record = validate_document(
        contract, _document(contract, tuple(values)), _provenance(contract)
    )[0]

    assert record.values["order_timestamp"].utcoffset() == offset


@pytest.mark.parametrize("source_value", ["2026-08-09T18:30:00", "not-a-timestamp"])
def test_naive_or_malformed_timestamp_is_rejected(source_value: str) -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[1] = source_value

    with pytest.raises(RecordValidationError):
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )


@pytest.mark.parametrize(
    "invalid_timestamp",
    [
        "2026-08-09X18:30:00+02:00",
        "2026-08-09T18:30:00X123+02:00",
        "2026-08-09T18:30:00,123+02:00",
    ],
)
def test_non_governed_timestamp_separators_are_rejected(
    invalid_timestamp: str,
) -> None:
    contract = _contract("northstar.ecommerce_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[1] = invalid_timestamp

    with pytest.raises(RecordValidationError, match="ISO 8601") as captured:
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )

    assert captured.value.context["failure_category"] == "invalid_timestamp"
    assert invalid_timestamp not in captured.value.context.values()


@pytest.mark.parametrize("currency", ["EUR", "USD"])
def test_approved_currency_shape_is_accepted(currency: str) -> None:
    contract = _contract("northstar.product_catalog")
    values = ("SKU-1", "Widget", "CAT-1", "1", "1", currency)
    record = validate_document(
        contract, _document(contract, values), _provenance(contract)
    )[0]
    assert record.values["currency_code"] == currency


@pytest.mark.parametrize("currency", ["eur", "EU", "EURO", "ÉUR"])
def test_invalid_currency_shape_is_rejected(currency: str) -> None:
    contract = _contract("northstar.product_catalog")
    values = ("SKU-1", "Widget", "CAT-1", "1", "1", currency)
    with pytest.raises(RecordValidationError) as captured:
        validate_document(contract, _document(contract, values), _provenance(contract))
    assert captured.value.context["failure_category"] == "uppercase_currency_code"


def test_retail_terminal_id_and_provenance_are_preserved() -> None:
    contract = _contract("northstar.retail_sales")
    record = validate_document(
        contract, _document(contract, row_number=23), _provenance(contract)
    )[0]

    assert record.values["terminal_id"] == " Terminal 01 "
    assert record.provenance.contract_key == contract.key
    assert record.provenance.source_identifier.endswith("/v1/source.csv")
    assert record.provenance.content_sha256 is CONTENT_SHA256
    assert record.provenance.source_id is SOURCE_ID
    assert record.provenance.run_id is RUN_ID
    assert record.provenance.row_number == 23
    assert not hasattr(record, "database_id")


@pytest.mark.parametrize("field_index", range(8))
def test_every_retail_field_is_non_nullable(field_index: int) -> None:
    contract = _contract("northstar.retail_sales")
    values = list(VALID_ROWS[contract.key.source_contract_id])
    values[field_index] = ""

    with pytest.raises(RecordValidationError) as captured:
        validate_document(
            contract, _document(contract, tuple(values)), _provenance(contract)
        )

    assert captured.value.context["failure_category"] == "non_nullable_empty"


@pytest.mark.parametrize("contract_id", tuple(VALID_ROWS))
def test_header_only_document_is_rejected(contract_id: str) -> None:
    contract = _contract(contract_id)
    document = ParsedCsvDocument(tuple(field.name for field in contract.fields), ())

    with pytest.raises(RecordValidationError) as captured:
        validate_document(contract, document, _provenance(contract))

    assert captured.value.context["failure_category"] == "no_data_records"


def test_multiple_rows_are_atomic_when_one_is_invalid() -> None:
    contract = _contract("northstar.ecommerce_sales")
    valid = VALID_ROWS[contract.key.source_contract_id]
    invalid = list(valid)
    invalid[4] = "0"
    document = ParsedCsvDocument(
        tuple(field.name for field in contract.fields),
        (
            ParsedCsvRow(2, valid),
            ParsedCsvRow(3, tuple(invalid)),
            ParsedCsvRow(4, valid),
        ),
    )

    with pytest.raises(RecordValidationError):
        validate_document(contract, document, _provenance(contract))


def test_multiple_valid_rows_return_complete_immutable_tuple() -> None:
    contract = _contract("northstar.ecommerce_sales")
    valid = VALID_ROWS[contract.key.source_contract_id]
    document = ParsedCsvDocument(
        tuple(field.name for field in contract.fields),
        (ParsedCsvRow(2, valid), ParsedCsvRow(3, valid)),
    )

    records = validate_document(contract, document, _provenance(contract))

    assert isinstance(records, tuple)
    assert len(records) == 2
    with pytest.raises(TypeError):
        records[0] = records[1]  # type: ignore[index]


def test_contradictory_provenance_contract_identity_is_domain_error() -> None:
    contract = _contract("northstar.product_catalog")
    contradictory = _provenance(
        contract, contract_key=SourceContractKey("northstar.ecommerce_sales", 1)
    )

    with pytest.raises(ValueError, match="must match") as captured:
        validate_document(contract, _document(contract), contradictory)

    assert not isinstance(captured.value, RecordValidationError)
