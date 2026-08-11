"""Unit tests for the governed Northstar quality expectations."""

from dataclasses import replace
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
)
from sales_data_platform.quality.evaluation import evaluate_quality
from sales_data_platform.quality.expectations import (
    INCOHERENT_TRANSACTION_GROUP,
    PRODUCT_SKU_UNIQUENESS,
    SALES_TRANSACTION_CURRENCY_CONSISTENCY,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationScope,
    QualityOutcome,
    QualityOutcomeStatus,
)
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    CustomerReferenceState,
    TransformationRuleSetKey,
)


def _provenance(
    row: int, *, run: str = "12345678-1234-5678-1234-567812345678"
) -> RecordProvenance:
    key = SourceContractKey("northstar.test", 1)
    return RecordProvenance(
        key,
        "test/v1/data.csv",
        ContentSha256("a" * 64),
        SourceIdentity("source-1"),
        RunIdentity(UUID(run)),
        row,
    )


def _product(
    sku: str, row: int, *, run: str = "12345678-1234-5678-1234-567812345678"
) -> CanonicalProduct:
    provenance = _provenance(row, run=run)
    return CanonicalProduct(
        sku,
        f"Product {row}",
        "CATEGORY-A",
        Decimal("10.00"),
        Decimal("4.00"),
        "USD",
        provenance,
        TransformationRuleSetKey(provenance.contract_key, 1),
    )


def _line(
    transaction: str,
    currency: str,
    row: int,
    *,
    channel: str = "ECOMMERCE",
    run: str = "12345678-1234-5678-1234-567812345678",
) -> CanonicalSalesLine:
    provenance = _provenance(row, run=run)
    return CanonicalSalesLine(
        channel,
        transaction,
        datetime(2026, 1, 1, tzinfo=UTC),
        None,
        CustomerReferenceState.ABSENT,
        f"SKU-{row}",
        1,
        Decimal("10.00"),
        currency,
        Decimal("10.00"),
        {},
        provenance,
        TransformationRuleSetKey(provenance.contract_key, 1),
    )


def _evaluate(
    scope: list[CanonicalProduct] | list[CanonicalSalesLine], expectation: object
) -> QualityOutcome:
    return evaluate_quality(
        scope,
        evaluated_scope_reference="governed-scope:1",
        expectations=(expectation,),  # type: ignore[arg-type]
    ).outcomes[0]


def _semantic(outcome: QualityOutcome) -> tuple[object, ...]:
    return (
        outcome.expectation_key,
        outcome.status,
        outcome.disposition,
        outcome.affected_scope_reference,
        dict(outcome.evidence),
    )


def test_product_expectation_has_frozen_governance_metadata() -> None:
    definition = PRODUCT_SKU_UNIQUENESS.definition
    assert definition.key.expectation_id == "DQ-PRODUCT-001"
    assert definition.key.expectation_version == 1
    assert definition.canonical_scope == "CanonicalProduct"
    assert definition.evaluation_scope is QualityEvaluationScope.COLLECTION
    assert definition.violation_disposition is QualityDisposition.BLOCKING


def test_unique_product_skus_are_satisfied_without_mutation() -> None:
    products = [_product("SKU-A", 1), _product("SKU-B", 2)]
    before = list(products)

    outcome = _evaluate(products, PRODUCT_SKU_UNIQUENESS)

    assert outcome.status is QualityOutcomeStatus.SATISFIED
    assert products == before
    assert products[0] is before[0]


def test_duplicate_product_sku_is_blocking_with_safe_ordered_provenance() -> None:
    products = [_product("SKU-A", 1), _product("SKU-B", 2), _product("SKU-A", 3)]

    outcome = _evaluate(products, PRODUCT_SKU_UNIQUENESS)

    assert outcome.status is QualityOutcomeStatus.VIOLATED
    assert outcome.disposition is QualityDisposition.BLOCKING
    assert outcome.evidence == {
        "issue_code": "DUPLICATE_SKU",
        "duplicate_sku": "SKU-A",
        "affected_count": 2,
    }
    assert outcome.provenance == (products[0].provenance, products[2].provenance)
    assert "Product" not in repr(outcome.evidence)


def test_multiple_duplicate_skus_follow_governed_input_order() -> None:
    products = [
        _product("SKU-B", 1),
        _product("SKU-A", 2),
        _product("SKU-A", 3),
        _product("SKU-B", 4),
    ]

    outcome = _evaluate(products, PRODUCT_SKU_UNIQUENESS)

    assert outcome.evidence["duplicate_sku"] == "SKU-B"
    assert outcome.evidence["affected_count"] == 4
    assert outcome.provenance == tuple(product.provenance for product in products)


def test_product_semantics_ignore_run_identity_and_preserve_records() -> None:
    first = [_product("SKU-A", 1), _product("SKU-A", 2)]
    second = [
        _product("SKU-A", 1, run="87654321-4321-8765-4321-876543218765"),
        _product("SKU-A", 2, run="87654321-4321-8765-4321-876543218765"),
    ]
    snapshots = [replace(product) for product in first]

    first_outcome = _evaluate(first, PRODUCT_SKU_UNIQUENESS)
    second_outcome = _evaluate(second, PRODUCT_SKU_UNIQUENESS)

    assert _semantic(first_outcome) == _semantic(second_outcome)
    assert first_outcome != second_outcome
    assert first == snapshots


def test_product_expectation_rejects_invalid_canonical_scope() -> None:
    with pytest.raises(TypeError, match="CanonicalProduct"):
        _evaluate([_line("ORDER-1", "USD", 1)], PRODUCT_SKU_UNIQUENESS)


def test_sales_expectation_has_frozen_governance_metadata() -> None:
    definition = SALES_TRANSACTION_CURRENCY_CONSISTENCY.definition
    assert definition.key.expectation_id == "DQ-SALES-001"
    assert definition.key.expectation_version == 1
    assert definition.canonical_scope == "CanonicalSalesLine"
    assert definition.evaluation_scope is QualityEvaluationScope.GROUP
    assert definition.violation_disposition is QualityDisposition.BLOCKING


def test_coherent_single_currency_group_is_satisfied_without_mutation() -> None:
    lines = [_line("ORDER-1", "USD", 1), _line("ORDER-1", "USD", 2)]
    before = list(lines)

    outcome = _evaluate(lines, SALES_TRANSACTION_CURRENCY_CONSISTENCY)

    assert outcome.status is QualityOutcomeStatus.SATISFIED
    assert lines == before


def test_coherent_mixed_currency_group_is_blocking_with_ordered_provenance() -> None:
    lines = [_line("ORDER-1", "USD", 1), _line("ORDER-1", "EUR", 2)]

    outcome = _evaluate(lines, SALES_TRANSACTION_CURRENCY_CONSISTENCY)

    assert outcome.status is QualityOutcomeStatus.VIOLATED
    assert outcome.disposition is QualityDisposition.BLOCKING
    assert outcome.evidence == {
        "issue_code": "MIXED_TRANSACTION_CURRENCY",
        "affected_count": 2,
    }
    assert outcome.provenance == tuple(line.provenance for line in lines)
    assert "customer" not in repr(outcome.evidence).lower()


@pytest.mark.parametrize(
    "lines",
    [
        [],
        [_line("ORDER-1", "USD", 1), _line("ORDER-2", "USD", 2)],
        [
            _line("ORDER-1", "USD", 1, channel="ECOMMERCE"),
            _line("ORDER-1", "USD", 2, channel="RETAIL"),
        ],
    ],
)
def test_empty_or_incoherent_transaction_group_is_evaluation_error(
    lines: list[CanonicalSalesLine],
) -> None:
    outcome = _evaluate(lines, SALES_TRANSACTION_CURRENCY_CONSISTENCY)

    assert outcome.status is QualityOutcomeStatus.EVALUATION_ERROR
    assert outcome.evidence == {"reason_code": INCOHERENT_TRANSACTION_GROUP}


def test_sales_semantics_ignore_run_identity_and_preserve_records() -> None:
    first = [_line("ORDER-1", "USD", 1), _line("ORDER-1", "EUR", 2)]
    second = [
        _line("ORDER-1", "USD", 1, run="87654321-4321-8765-4321-876543218765"),
        _line("ORDER-1", "EUR", 2, run="87654321-4321-8765-4321-876543218765"),
    ]
    snapshots = [replace(line) for line in first]

    first_outcome = _evaluate(first, SALES_TRANSACTION_CURRENCY_CONSISTENCY)
    second_outcome = _evaluate(second, SALES_TRANSACTION_CURRENCY_CONSISTENCY)

    assert _semantic(first_outcome) == _semantic(second_outcome)
    assert first_outcome != second_outcome
    assert first == snapshots


def test_sales_expectation_rejects_invalid_canonical_scope() -> None:
    with pytest.raises(TypeError, match="CanonicalSalesLine"):
        _evaluate([_product("SKU-A", 1)], SALES_TRANSACTION_CURRENCY_CONSISTENCY)
