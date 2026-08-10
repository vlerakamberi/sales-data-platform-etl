"""Tests for immutable transformation domain and result models."""

from dataclasses import FrozenInstanceError, fields
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
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    CustomerReferenceState,
    TransformationBatchResult,
    TransformationOutcome,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)


@pytest.fixture
def contract_key() -> SourceContractKey:
    return SourceContractKey("northstar.ecommerce_sales", 1)


@pytest.fixture
def ruleset(contract_key: SourceContractKey) -> TransformationRuleSetKey:
    return TransformationRuleSetKey(contract_key, 1)


@pytest.fixture
def provenance(contract_key: SourceContractKey) -> RecordProvenance:
    return RecordProvenance(
        contract_key=contract_key,
        source_identifier="ecommerce_sales/v1/orders.csv",
        content_sha256=ContentSha256("a" * 64),
        source_id=SourceIdentity("source-1"),
        run_id=RunIdentity(UUID("12345678-1234-5678-1234-567812345678")),
        row_number=2,
    )


@pytest.fixture
def product(
    provenance: RecordProvenance, ruleset: TransformationRuleSetKey
) -> CanonicalProduct:
    return CanonicalProduct(
        sku="Sku-1",
        product_name="Product One",
        category_code="Category-A",
        list_price=Decimal("12.340"),
        unit_cost=Decimal("5.67"),
        product_currency_code="USD",
        provenance=provenance,
        ruleset=ruleset,
    )


def test_ruleset_accepts_positive_version_and_preserves_contract(
    contract_key: SourceContractKey,
) -> None:
    ruleset = TransformationRuleSetKey(contract_key, 2)

    assert ruleset.source_contract_key is contract_key
    assert ruleset.transformation_version == 2


@pytest.mark.parametrize("version", [0, -1, True])
def test_ruleset_rejects_non_positive_versions(
    contract_key: SourceContractKey, version: int
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        TransformationRuleSetKey(contract_key, version)


def test_models_are_immutable(product: CanonicalProduct) -> None:
    with pytest.raises(FrozenInstanceError):
        product.sku = "changed"  # type: ignore[misc]


def test_canonical_product_has_no_persistence_identity_fields() -> None:
    names = {field.name for field in fields(CanonicalProduct)}

    assert names == {
        "sku",
        "product_name",
        "category_code",
        "list_price",
        "unit_cost",
        "product_currency_code",
        "provenance",
        "ruleset",
    }


def test_canonical_sales_line_has_no_persistence_identity_fields() -> None:
    names = {field.name for field in fields(CanonicalSalesLine)}

    assert names == {
        "sales_channel_code",
        "source_transaction_number",
        "transaction_timestamp",
        "store_code",
        "customer_reference_state",
        "product_sku",
        "quantity",
        "unit_price",
        "currency_code",
        "line_amount",
        "source_local_context",
        "provenance",
        "ruleset",
    }


def test_sales_line_defensively_freezes_source_local_context(
    provenance: RecordProvenance, ruleset: TransformationRuleSetKey
) -> None:
    nested = ["lane-1"]
    context: dict[str, object] = {"terminal": nested}
    line = CanonicalSalesLine(
        "ECOMMERCE",
        "order-1",
        datetime(2026, 1, 1, tzinfo=UTC),
        None,
        CustomerReferenceState.ABSENT,
        "Sku-1",
        2,
        Decimal("1.25"),
        "USD",
        Decimal("2.50"),
        context,
        provenance,
        ruleset,
    )

    nested.append("lane-2")
    context["later"] = "value"

    assert line.source_local_context == {"terminal": ("lane-1",)}
    with pytest.raises(TypeError):
        line.source_local_context["terminal"] = "changed"  # type: ignore[index]


def test_approved_enums_have_exact_members() -> None:
    assert set(CustomerReferenceState) == {
        CustomerReferenceState.ABSENT,
        CustomerReferenceState.UNRESOLVED_SOURCE_REFERENCE,
    }
    assert set(TransformationOutcomeStatus) == {
        TransformationOutcomeStatus.SUCCESS,
        TransformationOutcomeStatus.UNTRANSFORMABLE,
        TransformationOutcomeStatus.AMBIGUOUS,
        TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
    }


def test_success_outcome_requires_record_and_forbids_issue(
    provenance: RecordProvenance,
    ruleset: TransformationRuleSetKey,
    product: CanonicalProduct,
) -> None:
    outcome = TransformationOutcome(
        TransformationOutcomeStatus.SUCCESS, provenance, ruleset, product
    )
    assert outcome.canonical_record is product
    assert outcome.provenance is provenance

    with pytest.raises(ValueError, match="requires a canonical record"):
        TransformationOutcome(TransformationOutcomeStatus.SUCCESS, provenance, ruleset)
    with pytest.raises(ValueError, match="failure details"):
        TransformationOutcome(
            TransformationOutcomeStatus.SUCCESS,
            provenance,
            ruleset,
            product,
            "INFO",
            "not permitted",
        )


def test_unsuccessful_outcome_requires_issue_and_forbids_record(
    provenance: RecordProvenance,
    ruleset: TransformationRuleSetKey,
    product: CanonicalProduct,
) -> None:
    with pytest.raises(ValueError, match="requires an issue"):
        TransformationOutcome(
            TransformationOutcomeStatus.UNTRANSFORMABLE, provenance, ruleset
        )
    with pytest.raises(ValueError, match="cannot contain a canonical record"):
        TransformationOutcome(
            TransformationOutcomeStatus.AMBIGUOUS,
            provenance,
            ruleset,
            product,
            "AMBIGUOUS_REFERENCE",
            "Reference is ambiguous",
        )


def test_batch_preserves_order_is_immutable_and_derives_counts(
    provenance: RecordProvenance,
    ruleset: TransformationRuleSetKey,
    product: CanonicalProduct,
) -> None:
    success = TransformationOutcome(
        TransformationOutcomeStatus.SUCCESS, provenance, ruleset, product
    )
    failure = TransformationOutcome(
        TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
        provenance,
        ruleset,
        issue_code="FRACTIONAL_QUANTITY",
        issue_message="Quantity must be integral",
    )
    supplied = [failure, success]
    batch = TransformationBatchResult(
        provenance.contract_key,
        provenance.source_id,
        provenance.run_id,
        ruleset,
        supplied,  # type: ignore[arg-type]
    )
    supplied.reverse()

    assert batch.outcomes == (failure, success)
    assert batch.record_count == 2
    assert batch.success_count == 1
    assert batch.failure_count == 1
    assert batch.successful_records == (product,)
    with pytest.raises(FrozenInstanceError):
        batch.ruleset = ruleset  # type: ignore[misc]


def test_batch_rejects_mismatched_outcome_identity(
    provenance: RecordProvenance,
    ruleset: TransformationRuleSetKey,
) -> None:
    other_ruleset = TransformationRuleSetKey(provenance.contract_key, 2)
    outcome = TransformationOutcome(
        TransformationOutcomeStatus.UNTRANSFORMABLE,
        provenance,
        other_ruleset,
        issue_code="UNSUPPORTED",
        issue_message="Cannot transform record",
    )

    with pytest.raises(ValueError, match="outcome rulesets"):
        TransformationBatchResult(
            provenance.contract_key,
            provenance.source_id,
            provenance.run_id,
            ruleset,
            (outcome,),
        )
