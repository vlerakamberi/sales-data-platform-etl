"""Tests for deterministic Data Quality evaluation mechanics."""

import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    ContentSha256,
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
)
from sales_data_platform.quality.evaluation import (
    CanonicalQualityScope,
    QualityConditionDecision,
    QualityEvaluationUnavailable,
    QualityExpectationExecution,
    evaluate_quality,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationScope,
    QualityExpectationDefinition,
    QualityExpectationKey,
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
    *, run_value: str = "12345678-1234-5678-1234-567812345678"
) -> RecordProvenance:
    contract_key = SourceContractKey("northstar.product_catalog", 1)
    return RecordProvenance(
        contract_key=contract_key,
        source_identifier="product_catalog/v1/products.csv",
        content_sha256=ContentSha256("a" * 64),
        source_id=SourceIdentity("source-1"),
        run_id=RunIdentity(UUID(run_value)),
        row_number=2,
    )


def _product(
    *, sku: str = "SKU-1", provenance: RecordProvenance | None = None
) -> CanonicalProduct:
    record_provenance = provenance or _provenance()
    return CanonicalProduct(
        sku=sku,
        product_name="Product One",
        category_code="CATEGORY-A",
        list_price=Decimal("10.00"),
        unit_cost=Decimal("4.00"),
        product_currency_code="USD",
        provenance=record_provenance,
        ruleset=TransformationRuleSetKey(record_provenance.contract_key, 1),
    )


def _sales_line() -> CanonicalSalesLine:
    provenance = _provenance()
    return CanonicalSalesLine(
        sales_channel_code="ECOMMERCE",
        source_transaction_number="ORDER-1",
        transaction_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        store_code=None,
        customer_reference_state=CustomerReferenceState.ABSENT,
        product_sku="SKU-1",
        quantity=2,
        unit_price=Decimal("5.00"),
        currency_code="USD",
        line_amount=Decimal("10.00"),
        source_local_context={},
        provenance=provenance,
        ruleset=TransformationRuleSetKey(provenance.contract_key, 1),
    )


def _definition(
    *,
    expectation_id: str = "test.expectation",
    evaluation_scope: QualityEvaluationScope = QualityEvaluationScope.RECORD,
    disposition: QualityDisposition = QualityDisposition.BLOCKING,
) -> QualityExpectationDefinition:
    return QualityExpectationDefinition(
        key=QualityExpectationKey(expectation_id, 1),
        description="Test-only quality behavior",
        business_rationale="Exercises evaluation mechanics only",
        canonical_scope="CanonicalProduct",
        evaluation_scope=evaluation_scope,
        violation_disposition=disposition,
    )


def _execution(
    *,
    definition: QualityExpectationDefinition | None = None,
    applicability: Callable[[CanonicalQualityScope], bool] = lambda _: True,
    condition: Callable[[CanonicalQualityScope], QualityConditionDecision] = lambda _: (
        QualityConditionDecision(True)
    ),
) -> QualityExpectationExecution:
    return QualityExpectationExecution(
        definition or _definition(), applicability, condition
    )


def _evaluate(
    canonical_scope: CanonicalProduct | tuple[CanonicalProduct, ...],
    *executions: QualityExpectationExecution,
) -> tuple[QualityOutcome, ...]:
    return evaluate_quality(
        canonical_scope,
        evaluated_scope_reference="governed-scope:1",
        expectations=executions,
    ).outcomes


def test_record_scope_maps_satisfied_and_reuses_provenance() -> None:
    product = _product()

    (outcome,) = _evaluate(product, _execution())

    assert outcome.status is QualityOutcomeStatus.SATISFIED
    assert outcome.disposition is None
    assert outcome.provenance == (product.provenance,)
    assert outcome.provenance[0] is product.provenance


@pytest.mark.parametrize(
    "disposition", [QualityDisposition.BLOCKING, QualityDisposition.NON_BLOCKING]
)
def test_business_violation_maps_disposition_without_exception_control_flow(
    disposition: QualityDisposition,
) -> None:
    calls = 0

    def violated(_: CanonicalQualityScope) -> QualityConditionDecision:
        nonlocal calls
        calls += 1
        return QualityConditionDecision(
            False,
            affected_scope_reference="product:SKU-1",
            evidence={"issue_code": "TEST_ONLY_VIOLATION"},
        )

    execution = _execution(
        definition=_definition(disposition=disposition), condition=violated
    )

    (outcome,) = _evaluate(_product(), execution)

    assert calls == 1
    assert outcome.status is QualityOutcomeStatus.VIOLATED
    assert outcome.disposition is disposition
    assert outcome.affected_scope_reference == "product:SKU-1"


def test_not_applicable_does_not_evaluate_condition_or_become_satisfied() -> None:
    def forbidden(_: CanonicalQualityScope) -> QualityConditionDecision:
        raise AssertionError("condition must not run")

    (outcome,) = _evaluate(
        _product(), _execution(applicability=lambda _: False, condition=forbidden)
    )

    assert outcome.status is QualityOutcomeStatus.NOT_APPLICABLE
    assert outcome.status is not QualityOutcomeStatus.SATISFIED
    assert outcome.disposition is None


@pytest.mark.parametrize("failure_stage", ["applicability", "condition"])
def test_known_evaluation_inability_maps_to_evaluation_error(
    failure_stage: str,
) -> None:
    def unavailable(_: CanonicalQualityScope) -> bool:
        raise QualityEvaluationUnavailable("TEST_REFERENCE_UNAVAILABLE")

    applicability = unavailable if failure_stage == "applicability" else lambda _: True
    condition = (
        unavailable
        if failure_stage == "condition"
        else lambda _: QualityConditionDecision(True)
    )
    execution = _execution(
        applicability=applicability,  # type: ignore[arg-type]
        condition=condition,  # type: ignore[arg-type]
    )

    (outcome,) = _evaluate(_product(), execution)

    assert outcome.status is QualityOutcomeStatus.EVALUATION_ERROR
    assert outcome.status is not QualityOutcomeStatus.VIOLATED
    assert outcome.evidence == {"reason_code": "TEST_REFERENCE_UNAVAILABLE"}


@pytest.mark.parametrize(
    ("applicability", "condition", "message"),
    [
        (None, lambda _: QualityConditionDecision(True), "Applicability"),
        (lambda _: True, None, "Quality-condition"),
    ],
)
def test_invalid_execution_configuration_fails_explicitly(
    applicability: object, condition: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        QualityExpectationExecution(
            _definition(),
            applicability,
            condition,  # type: ignore[arg-type]
        )


def test_invalid_behavior_return_types_fail_explicitly() -> None:
    with pytest.raises(TypeError, match="Applicability behavior"):
        _evaluate(_product(), _execution(applicability=lambda _: "yes"))  # type: ignore[arg-type,return-value]
    with pytest.raises(TypeError, match="Quality-condition behavior"):
        _evaluate(_product(), _execution(condition=lambda _: True))  # type: ignore[arg-type,return-value]


def test_unexpected_programming_exception_propagates() -> None:
    def defective(_: CanonicalQualityScope) -> QualityConditionDecision:
        raise RuntimeError("programming defect")

    with pytest.raises(RuntimeError, match="programming defect"):
        _evaluate(_product(), _execution(condition=defective))


def test_supplied_expectation_order_is_preserved() -> None:
    executions = [
        _execution(definition=_definition(expectation_id="test.second")),
        _execution(definition=_definition(expectation_id="test.first")),
    ]

    outcomes = _evaluate(_product(), *executions)

    assert [outcome.expectation_key.expectation_id for outcome in outcomes] == [
        "test.second",
        "test.first",
    ]
    assert [execution.definition.key.expectation_id for execution in executions] == [
        "test.second",
        "test.first",
    ]


@pytest.mark.parametrize(
    "evaluation_scope",
    [QualityEvaluationScope.COLLECTION, QualityEvaluationScope.GROUP],
)
def test_collection_and_group_scopes_preserve_order_and_explicit_provenance(
    evaluation_scope: QualityEvaluationScope,
) -> None:
    first = _product(sku="SKU-2")
    second = _product(sku="SKU-1")
    supplied = [first, second]

    def inspect(scope: CanonicalQualityScope) -> QualityConditionDecision:
        assert isinstance(scope, tuple)
        assert [record.sku for record in scope] == ["SKU-2", "SKU-1"]
        return QualityConditionDecision(True, provenance=(second.provenance,))

    outcomes = evaluate_quality(
        supplied,
        evaluated_scope_reference="products:all",
        expectations=(
            _execution(
                definition=_definition(evaluation_scope=evaluation_scope),
                condition=inspect,
            ),
        ),
    ).outcomes

    assert [record.sku for record in supplied] == ["SKU-2", "SKU-1"]
    assert outcomes[0].provenance == (second.provenance,)


def test_scope_shape_mismatch_is_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="RECORD"):
        _evaluate(
            (_product(),),
            _execution(
                definition=_definition(evaluation_scope=QualityEvaluationScope.RECORD)
            ),
        )
    with pytest.raises(ValueError, match="COLLECTION and GROUP"):
        _evaluate(
            _product(),
            _execution(
                definition=_definition(evaluation_scope=QualityEvaluationScope.GROUP)
            ),
        )


def test_accepts_only_actual_canonical_types() -> None:
    (sales_outcome,) = evaluate_quality(
        _sales_line(),
        evaluated_scope_reference="sales-line:1",
        expectations=(_execution(),),
    ).outcomes
    assert sales_outcome.status is QualityOutcomeStatus.SATISFIED

    with pytest.raises(TypeError, match="canonical records"):
        evaluate_quality(
            [object()],  # type: ignore[list-item]
            evaluated_scope_reference="invalid:1",
            expectations=(_execution(),),
        )


def test_canonical_input_and_nested_state_are_not_mutated() -> None:
    product = _product()
    before = replace(product)

    _evaluate(product, _execution(condition=lambda _: QualityConditionDecision(True)))

    assert product == before
    assert product.provenance is before.provenance
    assert product.ruleset is before.ruleset


def _semantic_outcomes(outcomes: tuple[QualityOutcome, ...]) -> tuple[object, ...]:
    return tuple(
        (
            outcome.expectation_key,
            outcome.status,
            outcome.evaluated_scope_reference,
            outcome.disposition,
            outcome.affected_scope_reference,
            dict(outcome.evidence),
        )
        for outcome in outcomes
    )


def test_deterministic_replay_ignores_traceability_only_run_identity() -> None:
    first = _product()
    second = _product(
        provenance=_provenance(run_value="87654321-4321-8765-4321-876543218765")
    )
    execution = _execution(
        condition=lambda _: QualityConditionDecision(
            False,
            affected_scope_reference="product:SKU-1",
            evidence={"issue_code": "TEST_ONLY_VIOLATION"},
        )
    )

    first_outcomes = _evaluate(first, execution)
    second_outcomes = _evaluate(second, execution)

    assert _semantic_outcomes(first_outcomes) == _semantic_outcomes(second_outcomes)
    assert first_outcomes != second_outcomes
    assert (
        first_outcomes[0].provenance[0].run_id
        != second_outcomes[0].provenance[0].run_id
    )


def test_evaluation_is_independent_of_current_working_directory(
    tmp_path: Path,
) -> None:
    execution = _execution()
    product = _product()
    original_cwd = Path.cwd()
    try:
        first = _evaluate(product, execution)
        os.chdir(tmp_path)
        second = _evaluate(product, execution)
    finally:
        os.chdir(original_cwd)

    assert first == second


def test_evaluation_module_has_no_database_or_production_expectation_surface() -> None:
    import sales_data_platform.quality.evaluation as evaluation

    assert not hasattr(evaluation, "psycopg")
    assert not hasattr(evaluation, "DQ_PRODUCT_001")
    assert not hasattr(evaluation, "DQ_SALES_001")
    assert not hasattr(evaluation, "violation_rate")
    assert not hasattr(evaluation, "quality_score")
