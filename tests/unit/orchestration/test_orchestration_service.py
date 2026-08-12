"""Unit tests for deterministic pipeline orchestration policy."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.errors import IngestionError
from sales_data_platform.ingestion.models import (
    RunIdentity,
    SourceIdentity,
    ValidatedBatch,
)
from sales_data_platform.orchestration import service
from sales_data_platform.orchestration.errors import OrchestrationPersistenceError
from sales_data_platform.orchestration.models import (
    FailureClassification,
    PipelineExecutionId,
    PipelineLifecycleState,
    StageIdentity,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationResult,
    QualityExpectationKey,
    QualityOutcome,
    QualityOutcomeStatus,
)
from sales_data_platform.transformation.models import (
    TransformationBatchResult,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)

NOW = datetime(2026, 8, 12, tzinfo=UTC)
PRODUCT = SourceContractKey("northstar.product_catalog", 1)
ECOMMERCE = SourceContractKey("northstar.ecommerce_sales", 1)
RETAIL = SourceContractKey("northstar.retail_sales", 1)


def _batch(key: SourceContractKey) -> ValidatedBatch:
    return ValidatedBatch(key, SourceIdentity("source"), RunIdentity(uuid4()), ())


def _transformed(key: SourceContractKey) -> TransformationBatchResult:
    batch = _batch(key)
    ruleset = TransformationRuleSetKey(key, 1)
    return TransformationBatchResult(key, batch.source_id, batch.run_id, ruleset, ())


def _quality(
    status: QualityOutcomeStatus = QualityOutcomeStatus.SATISFIED,
    disposition: QualityDisposition | None = None,
) -> QualityEvaluationResult:
    return QualityEvaluationResult(
        (
            QualityOutcome(
                QualityExpectationKey("DQ-TEST", 1),
                status,
                "scope",
                disposition=disposition,
                affected_scope_reference="affected"
                if status is QualityOutcomeStatus.VIOLATED
                else None,
            ),
        )
    )


def _wire(monkeypatch: pytest.MonkeyPatch, key: SourceContractKey = PRODUCT):
    calls: list[tuple[object, ...]] = []
    final = SimpleNamespace(state=PipelineLifecycleState.SUCCEEDED)
    names = (
        "create_pipeline_execution",
        "mark_pipeline_running",
        "mark_stage_running",
        "mark_stage_succeeded",
        "mark_stage_failed",
        "mark_stage_skipped",
        "mark_pipeline_succeeded",
        "mark_pipeline_blocked",
        "mark_pipeline_failed",
    )
    for name in names:
        monkeypatch.setattr(
            service,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, *args[1:])),
        )
    monkeypatch.setattr(service, "read_execution", lambda *_: final)
    monkeypatch.setattr(service, "_now", lambda: NOW)
    monkeypatch.setattr(service, "ingest_source_file", lambda *_a, **_k: _batch(key))
    monkeypatch.setattr(service, "transform_batch", lambda *_a, **_k: _transformed(key))
    monkeypatch.setattr(service, "_evaluate_data_quality", lambda *_: (_quality(),))
    return calls, final


def _run(key: SourceContractKey = PRODUCT, predecessor=None):
    return service.run_pipeline(
        object(),
        contract_key=key,
        source_path=Path("source.csv"),
        settings=Settings(_env_file=None),
        predecessor_execution_id=predecessor,
    )


def test_happy_path_orders_history_and_returns_authoritative_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, final = _wire(monkeypatch)
    result = _run()
    assert result is final
    assert [call[0] for call in calls] == [
        "create_pipeline_execution",
        "mark_pipeline_running",
        "mark_stage_running",
        "mark_stage_succeeded",
        "mark_stage_running",
        "mark_stage_succeeded",
        "mark_stage_running",
        "mark_stage_succeeded",
        "mark_pipeline_succeeded",
    ]
    assert [call[2] for call in calls if call[0] == "mark_stage_running"] == list(
        StageIdentity
    )


def test_fresh_execution_id_per_invocation_and_predecessor_is_only_propagated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, _ = _wire(monkeypatch)
    predecessor = PipelineExecutionId(uuid4())
    _run(predecessor=predecessor)
    _run()
    creates = [call for call in calls if call[0] == "create_pipeline_execution"]
    assert creates[0][1] != creates[1][1]
    assert creates[0][-1] == predecessor
    assert creates[1][-1] is None


@pytest.mark.parametrize("key", [PRODUCT, ECOMMERCE, RETAIL])
def test_all_contracts_use_transformation_version_one(
    monkeypatch: pytest.MonkeyPatch, key: SourceContractKey
) -> None:
    _wire(monkeypatch, key)
    seen = []

    def transform(batch, *, ruleset):
        seen.append(ruleset)
        return _transformed(key)

    monkeypatch.setattr(service, "transform_batch", transform)
    _run(key)
    assert seen == [TransformationRuleSetKey(key, 1)]


def test_exact_dq_mapping_and_deterministic_sales_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = SimpleNamespace()
    monkeypatch.setattr(service, "CanonicalProduct", type(product))
    transformed = SimpleNamespace(successful_records=(product,))
    seen = []
    monkeypatch.setattr(
        service,
        "evaluate_quality",
        lambda scope, **kwargs: seen.append((scope, kwargs)) or _quality(),
    )
    service._evaluate_data_quality(PRODUCT, transformed)
    assert seen[0][1]["evaluated_scope_reference"] == "product-catalog:v1"
    assert seen[0][1]["expectations"] == (service.PRODUCT_SKU_UNIQUENESS,)

    class Sales:
        def __init__(self, channel, transaction):
            self.sales_channel_code = channel
            self.source_transaction_number = transaction

    monkeypatch.setattr(service, "CanonicalSalesLine", Sales)
    seen.clear()
    transformed.successful_records = (
        Sales("RETAIL", "B"),
        Sales("RETAIL", "A"),
        Sales("RETAIL", "B"),
    )
    service._evaluate_data_quality(RETAIL, transformed)
    assert [item[1]["evaluated_scope_reference"] for item in seen] == [
        "sales-transaction:RETAIL:A",
        "sales-transaction:RETAIL:B",
    ]
    assert all(
        item[1]["expectations"] == (service.SALES_TRANSACTION_CURRENCY_CONSISTENCY,)
        for item in seen
    )


@pytest.mark.parametrize(
    ("quality", "terminal"),
    [
        (_quality(), "mark_pipeline_succeeded"),
        (_quality(QualityOutcomeStatus.NOT_APPLICABLE), "mark_pipeline_succeeded"),
        (
            _quality(QualityOutcomeStatus.VIOLATED, QualityDisposition.NON_BLOCKING),
            "mark_pipeline_succeeded",
        ),
        (
            _quality(QualityOutcomeStatus.VIOLATED, QualityDisposition.BLOCKING),
            "mark_pipeline_blocked",
        ),
    ],
)
def test_quality_aggregation(monkeypatch, quality, terminal) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(service, "_evaluate_data_quality", lambda *_: (quality,))
    _run()
    assert terminal in [call[0] for call in calls]


def test_evaluation_error_fails_dq_and_pipeline(monkeypatch) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "_evaluate_data_quality",
        lambda *_: (_quality(QualityOutcomeStatus.EVALUATION_ERROR),),
    )
    _run()
    failed = [call for call in calls if call[0] == "mark_stage_failed"]
    assert failed[0][2] is StageIdentity.DATA_QUALITY
    assert (
        failed[0][-1].category is FailureClassification.DATA_QUALITY_EVALUATION_FAILURE
    )
    assert failed[0][-1].code == "DATA_QUALITY_EVALUATION_ERROR"


def test_coordinator_owned_invalid_dq_scope_is_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "_evaluate_data_quality",
        lambda *_: (_ for _ in ()).throw(
            service._DQConfigurationError("coordinator-owned validation")
        ),
    )

    _run()

    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert (failure.category, failure.code) == (
        FailureClassification.CONFIGURATION_FAILURE,
        "CONFIGURATION_ERROR",
    )


@pytest.mark.parametrize("error", [TypeError("unexpected"), ValueError("unexpected")])
def test_unexpected_dq_callable_type_or_value_error_is_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(
        service,
        "_evaluate_data_quality",
        lambda *_: (_ for _ in ()).throw(error),
    )

    _run()

    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert (failure.category, failure.code) == (
        FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
        "UNEXPECTED_EXECUTION_ERROR",
    )


def test_invalid_returned_dq_result_is_invalid_stage_result(monkeypatch) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(service, "_evaluate_data_quality", lambda *_: (object(),))

    _run()

    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert (failure.category, failure.code) == (
        FailureClassification.INVALID_STAGE_RESULT,
        "INVALID_STAGE_RESULT",
    )


@pytest.mark.parametrize(
    ("error", "classification", "code"),
    [
        (
            IngestionError("controlled"),
            FailureClassification.INGESTION_FAILURE,
            "INGESTION_ERROR",
        ),
        (
            RuntimeError("unexpected"),
            FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
            "UNEXPECTED_EXECUTION_ERROR",
        ),
    ],
)
def test_ingestion_failures_skip_both_downstream_stages(
    monkeypatch, error, classification, code
) -> None:
    calls, _ = _wire(monkeypatch)
    monkeypatch.setattr(
        service, "ingest_source_file", lambda *_a, **_k: (_ for _ in ()).throw(error)
    )
    _run()
    skips = [call[2] for call in calls if call[0] == "mark_stage_skipped"]
    assert skips == [StageIdentity.TRANSFORMATION, StageIdentity.DATA_QUALITY]
    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert (failure.category, failure.code) == (classification, code)


def test_unsuccessful_transformation_fails_and_skips_dq(monkeypatch) -> None:
    calls, _ = _wire(monkeypatch)
    transformed = _transformed(PRODUCT)
    outcome = SimpleNamespace(status=TransformationOutcomeStatus.UNTRANSFORMABLE)
    object.__setattr__(transformed, "outcomes", (outcome,))
    monkeypatch.setattr(service, "transform_batch", lambda *_a, **_k: transformed)
    _run()
    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert failure.code == "TRANSFORMATION_UNSUCCESSFUL_OUTCOME"
    assert StageIdentity.DATA_QUALITY in [
        call[2] for call in calls if call[0] == "mark_stage_skipped"
    ]


def test_unsupported_contract_is_controlled_configuration_failure(monkeypatch) -> None:
    calls, _ = _wire(monkeypatch)
    _run(SourceContractKey("unknown", 1))
    assert not any(call[0] == "mark_stage_running" for call in calls)
    failure = next(call[-1] for call in calls if call[0] == "mark_pipeline_failed")
    assert failure.category is FailureClassification.CONFIGURATION_FAILURE


@pytest.mark.parametrize(
    "failing_operation",
    [
        "create_pipeline_execution",
        "mark_pipeline_running",
        "mark_stage_running",
        "mark_stage_succeeded",
        "mark_stage_failed",
        "mark_stage_skipped",
        "mark_pipeline_succeeded",
    ],
)
def test_persistence_failure_propagates_without_retry_or_downstream_work(
    monkeypatch: pytest.MonkeyPatch, failing_operation: str
) -> None:
    calls, _ = _wire(monkeypatch)
    original = getattr(service, failing_operation)
    count = 0

    def fail_once(*args, **kwargs):
        nonlocal count
        count += 1
        raise OrchestrationPersistenceError("controlled")

    monkeypatch.setattr(service, failing_operation, fail_once)
    if failing_operation in {"mark_stage_failed", "mark_stage_skipped"}:
        monkeypatch.setattr(
            service,
            "ingest_source_file",
            lambda *_a, **_k: (_ for _ in ()).throw(IngestionError("failure")),
        )
    with pytest.raises(OrchestrationPersistenceError):
        _run()
    assert count == 1
    assert original is not None
