"""Tests for deterministic transformation service outcome accounting."""

import ast
import inspect
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
    ValidatedBatch,
    ValidatedRecord,
)
from sales_data_platform.transformation import mapping
from sales_data_platform.transformation import service as transformation_service
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    TransformationOutcome,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.service import transform_batch


def _record(
    contract_key: SourceContractKey,
    row_number: int,
    values: dict[str, object],
) -> ValidatedRecord:
    return ValidatedRecord(
        values,
        RecordProvenance(
            contract_key=contract_key,
            source_identifier="governed/source.csv",
            content_sha256=ContentSha256("c" * 64),
            source_id=SourceIdentity("source-identity"),
            run_id=RunIdentity(UUID("12345678-1234-5678-1234-567812345678")),
            row_number=row_number,
        ),
    )


def _batch(*records: ValidatedRecord) -> ValidatedBatch:
    first = records[0]
    return ValidatedBatch(
        first.provenance.contract_key,
        first.provenance.source_id,
        first.provenance.run_id,
        records,
    )


def _ruleset(contract_key: SourceContractKey) -> TransformationRuleSetKey:
    return TransformationRuleSetKey(contract_key, 1)


def _product(row_number: int = 2, *, consistent: bool = True) -> ValidatedRecord:
    return _record(
        mapping.PRODUCT_CATALOG_V1,
        row_number,
        {
            "sku": f"SKU-{row_number}",
            "product_name": "Product",
            "category_code": "CATEGORY",
            "list_price": Decimal("10.00"),
            "unit_cost": Decimal("4.00"),
            "currency_code": "USD" if consistent else None,
        },
    )


def _ecommerce(
    row_number: int = 2,
    *,
    quantity: Decimal = Decimal("2"),
    customer_email: str | None = None,
) -> ValidatedRecord:
    return _record(
        mapping.ECOMMERCE_SALES_V1,
        row_number,
        {
            "order_number": f"ORDER-{row_number}",
            "order_timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "customer_email": customer_email,
            "sku": f"SKU-{row_number}",
            "quantity": quantity,
            "unit_price": Decimal("3.25"),
            "currency_code": "USD",
        },
    )


def _retail(row_number: int = 2) -> ValidatedRecord:
    return _record(
        mapping.RETAIL_SALES_V1,
        row_number,
        {
            "receipt_number": f"RECEIPT-{row_number}",
            "transaction_timestamp": datetime(2026, 1, 1, tzinfo=UTC),
            "store_code": "STORE-1",
            "terminal_id": "TERMINAL-1",
            "sku": f"SKU-{row_number}",
            "quantity": Decimal("1"),
            "unit_price": Decimal("5.00"),
            "currency_code": "USD",
        },
    )


@pytest.mark.parametrize(
    ("record", "expected_type"),
    [
        (_product(), CanonicalProduct),
        (_ecommerce(), CanonicalSalesLine),
        (_retail(), CanonicalSalesLine),
    ],
)
def test_dispatches_exact_mapper_and_preserves_batch_identity(
    record: ValidatedRecord,
    expected_type: type[CanonicalProduct] | type[CanonicalSalesLine],
) -> None:
    batch = _batch(record)
    ruleset = _ruleset(batch.contract_key)

    result = transform_batch(batch, ruleset=ruleset)

    assert result.source_contract_key is batch.contract_key
    assert result.source_id is batch.source_id
    assert result.run_id is batch.run_id
    assert result.ruleset is ruleset
    assert isinstance(result.successful_records[0], expected_type)


def test_rejects_ruleset_batch_contract_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        transform_batch(_batch(_product()), ruleset=_ruleset(mapping.RETAIL_SALES_V1))


def test_unsupported_batch_contract_is_explicit_even_when_empty() -> None:
    key = SourceContractKey("northstar.product_catalog", 2)
    batch = ValidatedBatch(
        key,
        SourceIdentity("source-identity"),
        RunIdentity(UUID("12345678-1234-5678-1234-567812345678")),
        (),
    )

    with pytest.raises(mapping.UnsupportedSourceContractError, match="Unsupported"):
        transform_batch(batch, ruleset=_ruleset(key))


def test_mixed_outcomes_preserve_order_provenance_and_accounting() -> None:
    records = (_product(2), _product(3, consistent=False), _product(4))
    result = transform_batch(
        _batch(*records), ruleset=_ruleset(mapping.PRODUCT_CATALOG_V1)
    )

    assert tuple(outcome.status for outcome in result.outcomes) == (
        TransformationOutcomeStatus.SUCCESS,
        TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
        TransformationOutcomeStatus.SUCCESS,
    )
    assert tuple(outcome.provenance for outcome in result.outcomes) == tuple(
        record.provenance for record in records
    )
    assert result.record_count == len(records)
    assert result.success_count == 2
    assert result.failure_count == 1
    assert len(result.successful_records) == 2
    failure = result.outcomes[1]
    assert failure.canonical_record is None
    assert failure.issue_code == "BUSINESS_RULE_VIOLATION"
    assert "USD" not in failure.issue_message


def test_fractional_quantity_becomes_business_rule_rejection() -> None:
    record = _ecommerce(quantity=Decimal("1.5"))

    outcome = transform_batch(
        _batch(record), ruleset=_ruleset(mapping.ECOMMERCE_SALES_V1)
    ).outcomes[0]

    assert outcome.status is TransformationOutcomeStatus.BUSINESS_RULE_REJECTED
    assert outcome.provenance is record.provenance


def test_controlled_mapping_failure_becomes_untransformable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _retail()

    def controlled_failure(*args: object) -> None:
        raise mapping.TransformationMappingError("sensitive raw value")

    monkeypatch.setattr(mapping, "map_validated_record", controlled_failure)
    outcome = transform_batch(
        _batch(record), ruleset=_ruleset(mapping.RETAIL_SALES_V1)
    ).outcomes[0]

    assert outcome.status is TransformationOutcomeStatus.UNTRANSFORMABLE
    assert outcome.provenance is record.provenance
    assert "sensitive raw value" not in outcome.issue_message


def test_unexpected_failures_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    def programming_failure(*args: object) -> None:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(mapping, "map_validated_record", programming_failure)
    with pytest.raises(RuntimeError, match="programming defect"):
        transform_batch(
            _batch(_product()), ruleset=_ruleset(mapping.PRODUCT_CATALOG_V1)
        )


def test_ambiguity_has_narrow_governed_outcome_construction_path() -> None:
    record = _product()
    ruleset = _ruleset(mapping.PRODUCT_CATALOG_V1)

    outcome = TransformationOutcome(
        status=TransformationOutcomeStatus.AMBIGUOUS,
        provenance=record.provenance,
        ruleset=ruleset,
        issue_code="AMBIGUOUS_REFERENCE",
        issue_message="Reference has multiple governed interpretations",
    )

    assert outcome.status is TransformationOutcomeStatus.AMBIGUOUS
    assert outcome.canonical_record is None


def test_repeated_transformation_is_deterministic() -> None:
    batch = _batch(_ecommerce(2), _ecommerce(3, quantity=Decimal("2.5")))
    ruleset = _ruleset(mapping.ECOMMERCE_SALES_V1)

    assert transform_batch(batch, ruleset=ruleset) == transform_batch(
        batch, ruleset=ruleset
    )


def test_lifecycle_logs_are_safe_and_service_has_no_database_access(
    caplog: pytest.LogCaptureFixture,
) -> None:
    email = "private.customer@example.com"
    record = _ecommerce(customer_email=email)
    with caplog.at_level(
        logging.INFO, logger="sales_data_platform.transformation.service"
    ):
        result = transform_batch(
            _batch(record), ruleset=_ruleset(mapping.ECOMMERCE_SALES_V1)
        )

    assert result.success_count == 1
    assert "Transformation started" in caplog.text
    assert "Transformation completed" in caplog.text
    assert email not in caplog.text

    service_tree = ast.parse(inspect.getsource(transformation_service))
    imported_modules = {
        alias.name
        for node in ast.walk(service_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(service_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not any(
        module == "psycopg" or module.startswith("sales_data_platform.database")
        for module in imported_modules
    )
    assert not any(
        inspect.ismodule(value)
        and (
            value.__name__ == "psycopg"
            or value.__name__.startswith("sales_data_platform.database")
        )
        for value in vars(transformation_service).values()
    )
