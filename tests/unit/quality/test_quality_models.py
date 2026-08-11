"""Tests for immutable Data Quality domain contracts."""

from dataclasses import FrozenInstanceError, fields
from enum import Enum
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationResult,
    QualityEvaluationScope,
    QualityExpectationDefinition,
    QualityExpectationKey,
    QualityOutcome,
    QualityOutcomeStatus,
)


@pytest.fixture
def expectation_key() -> QualityExpectationKey:
    return QualityExpectationKey("northstar.sales.currency_consistency", 1)


@pytest.fixture
def provenance() -> RecordProvenance:
    return RecordProvenance(
        contract_key=SourceContractKey("northstar.ecommerce_sales", 1),
        source_identifier="ecommerce_sales/v1/orders.csv",
        content_sha256=ContentSha256("a" * 64),
        source_id=SourceIdentity("source-1"),
        run_id=RunIdentity(UUID("12345678-1234-5678-1234-567812345678")),
        row_number=2,
    )


def test_expectation_key_is_validated_semantic_identity() -> None:
    key = QualityExpectationKey("northstar.product.sku_present", 2)

    assert key.expectation_id == "northstar.product.sku_present"
    assert key.expectation_version == 2
    assert not hasattr(key, "run_id")
    assert not hasattr(key, "timestamp")
    assert not hasattr(key, "git_sha")
    with pytest.raises(FrozenInstanceError):
        key.expectation_version = 3  # type: ignore[misc]


@pytest.mark.parametrize("expectation_id", ["", " ", None])
def test_expectation_key_rejects_nonblank_id(expectation_id: object) -> None:
    with pytest.raises(ValueError, match="Expectation ID"):
        QualityExpectationKey(expectation_id, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("version", [0, -1, True, 1.5])
def test_expectation_key_requires_positive_integer_version(version: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        QualityExpectationKey("northstar.product.sku_present", version)  # type: ignore[arg-type]


def test_approved_enums_have_exact_members() -> None:
    assert set(QualityDisposition) == {
        QualityDisposition.BLOCKING,
        QualityDisposition.NON_BLOCKING,
    }
    assert set(QualityEvaluationScope) == {
        QualityEvaluationScope.RECORD,
        QualityEvaluationScope.COLLECTION,
        QualityEvaluationScope.GROUP,
    }
    assert set(QualityOutcomeStatus) == {
        QualityOutcomeStatus.SATISFIED,
        QualityOutcomeStatus.VIOLATED,
        QualityOutcomeStatus.NOT_APPLICABLE,
        QualityOutcomeStatus.EVALUATION_ERROR,
    }


def test_no_severity_hierarchy_exists() -> None:
    for name in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        assert not hasattr(QualityDisposition, name)


def test_expectation_definition_is_narrow_and_immutable(
    expectation_key: QualityExpectationKey,
) -> None:
    definition = QualityExpectationDefinition(
        key=expectation_key,
        description="Transaction currencies agree within one governed order",
        business_rationale="Mixed currencies make order totals uninterpretable",
        canonical_scope="CanonicalSalesLine",
        evaluation_scope=QualityEvaluationScope.GROUP,
        violation_disposition=QualityDisposition.BLOCKING,
    )

    assert definition.key is expectation_key
    assert definition.canonical_scope == "CanonicalSalesLine"
    assert definition.evaluation_scope is QualityEvaluationScope.GROUP
    with pytest.raises(FrozenInstanceError):
        definition.description = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field_name", ["description", "business_rationale", "canonical_scope"]
)
def test_expectation_definition_rejects_blank_text(
    expectation_key: QualityExpectationKey, field_name: str
) -> None:
    values = {
        "key": expectation_key,
        "description": "Description",
        "business_rationale": "Rationale",
        "canonical_scope": "CanonicalProduct",
        "evaluation_scope": QualityEvaluationScope.RECORD,
        "violation_disposition": QualityDisposition.NON_BLOCKING,
    }
    values[field_name] = " "

    with pytest.raises(ValueError, match="non-empty string"):
        QualityExpectationDefinition(**values)  # type: ignore[arg-type]


def test_valid_satisfied_outcome_has_no_violation_semantics(
    expectation_key: QualityExpectationKey, provenance: RecordProvenance
) -> None:
    outcome = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.SATISFIED,
        "order:1001",
        provenance=(provenance,),
        evidence={"currency": "USD"},
    )

    assert outcome.disposition is None
    assert outcome.affected_scope_reference is None
    assert outcome.provenance == (provenance,)


@pytest.mark.parametrize(
    "disposition", [QualityDisposition.BLOCKING, QualityDisposition.NON_BLOCKING]
)
def test_valid_violated_outcome_requires_governed_disposition(
    expectation_key: QualityExpectationKey,
    provenance: RecordProvenance,
    disposition: QualityDisposition,
) -> None:
    outcome = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.VIOLATED,
        "order:1001",
        disposition=disposition,
        affected_scope_reference="order:1001",
        provenance=(provenance,),
        evidence={"issue_code": "MIXED_CURRENCY"},
    )

    assert outcome.disposition is disposition
    assert outcome.affected_scope_reference == "order:1001"


def test_valid_not_applicable_is_not_satisfied(
    expectation_key: QualityExpectationKey,
) -> None:
    outcome = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.NOT_APPLICABLE,
        "product:SKU-1",
        evidence={"reason_code": "NOT_A_SALES_LINE"},
    )

    assert outcome.status is QualityOutcomeStatus.NOT_APPLICABLE
    assert outcome.status is not QualityOutcomeStatus.SATISFIED


def test_valid_evaluation_error_is_not_violation_or_success(
    expectation_key: QualityExpectationKey,
) -> None:
    outcome = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.EVALUATION_ERROR,
        "order:1001",
        evidence={"reason_code": "REFERENCE_INPUT_UNAVAILABLE"},
    )

    assert outcome.status is QualityOutcomeStatus.EVALUATION_ERROR
    assert outcome.status is not QualityOutcomeStatus.VIOLATED
    assert outcome.status is not QualityOutcomeStatus.SATISFIED
    assert outcome.disposition is None


@pytest.mark.parametrize(
    "status",
    [
        QualityOutcomeStatus.SATISFIED,
        QualityOutcomeStatus.NOT_APPLICABLE,
        QualityOutcomeStatus.EVALUATION_ERROR,
    ],
)
def test_non_violation_rejects_disposition(
    expectation_key: QualityExpectationKey, status: QualityOutcomeStatus
) -> None:
    with pytest.raises(ValueError, match="Only a violated outcome"):
        QualityOutcome(
            expectation_key,
            status,
            "scope:1",
            disposition=QualityDisposition.BLOCKING,
        )


def test_violation_rejects_missing_disposition_or_affected_scope(
    expectation_key: QualityExpectationKey,
) -> None:
    with pytest.raises(ValueError, match="requires a governed disposition"):
        QualityOutcome(
            expectation_key,
            QualityOutcomeStatus.VIOLATED,
            "scope:1",
            affected_scope_reference="scope:1",
        )
    with pytest.raises(ValueError, match="affected scope"):
        QualityOutcome(
            expectation_key,
            QualityOutcomeStatus.VIOLATED,
            "scope:1",
            disposition=QualityDisposition.NON_BLOCKING,
        )


def test_non_violation_rejects_affected_scope(
    expectation_key: QualityExpectationKey,
) -> None:
    with pytest.raises(ValueError, match="affected scope"):
        QualityOutcome(
            expectation_key,
            QualityOutcomeStatus.NOT_APPLICABLE,
            "scope:1",
            affected_scope_reference="scope:1",
        )


def test_evidence_is_safe_defensively_copied_and_immutable(
    expectation_key: QualityExpectationKey,
) -> None:
    supplied = {"issue_code": "MIXED_CURRENCY", "affected_count": 2}
    outcome = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.VIOLATED,
        "order:1001",
        disposition=QualityDisposition.BLOCKING,
        affected_scope_reference="order:1001",
        evidence=supplied,
    )
    supplied["customer_email"] = "sensitive@example.test"

    assert outcome.evidence == {
        "issue_code": "MIXED_CURRENCY",
        "affected_count": 2,
    }
    with pytest.raises(TypeError):
        outcome.evidence["issue_code"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError, match="unsupported value"):
        QualityOutcome(
            expectation_key,
            QualityOutcomeStatus.SATISFIED,
            "scope:1",
            evidence={"complete_record": {"sku": "SKU-1"}},  # type: ignore[dict-item]
        )


def test_outcome_reuses_zero_one_or_multiple_provenance_references(
    expectation_key: QualityExpectationKey, provenance: RecordProvenance
) -> None:
    without_provenance = QualityOutcome(
        expectation_key, QualityOutcomeStatus.SATISFIED, "collection:products"
    )
    supplied = [provenance, provenance]
    with_provenance = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.SATISFIED,
        "collection:products",
        provenance=supplied,  # type: ignore[arg-type]
    )
    supplied.clear()

    assert without_provenance.provenance == ()
    assert with_provenance.provenance == (provenance, provenance)
    assert with_provenance.provenance[0] is provenance


def test_outcome_and_ordered_result_are_deeply_immutable(
    expectation_key: QualityExpectationKey,
) -> None:
    first = QualityOutcome(
        expectation_key, QualityOutcomeStatus.SATISFIED, "product:SKU-1"
    )
    second = QualityOutcome(
        expectation_key,
        QualityOutcomeStatus.NOT_APPLICABLE,
        "product:SKU-2",
    )
    supplied = [second, first]
    result = QualityEvaluationResult(supplied)  # type: ignore[arg-type]
    supplied.reverse()

    assert result.outcomes == (second, first)
    with pytest.raises(FrozenInstanceError):
        first.status = QualityOutcomeStatus.VIOLATED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.outcomes = ()  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.outcomes[0] = first  # type: ignore[index]


def test_contracts_have_no_persistence_or_orchestration_state() -> None:
    forbidden = {
        "database_id",
        "result_id",
        "persisted_at",
        "retry_count",
        "workflow_state",
        "orchestration_state",
        "violation_rate",
        "blocking_violation_count",
        "quality_score",
    }

    for model in (
        QualityExpectationKey,
        QualityExpectationDefinition,
        QualityOutcome,
        QualityEvaluationResult,
    ):
        assert forbidden.isdisjoint(field.name for field in fields(model))


def test_quality_enums_do_not_define_generic_pass_fail() -> None:
    enum_members = {
        member.name
        for enum_type in (
            QualityDisposition,
            QualityEvaluationScope,
            QualityOutcomeStatus,
        )
        for member in enum_type
        if isinstance(member, Enum)
    }

    assert "PASS" not in enum_members
    assert "FAIL" not in enum_members
