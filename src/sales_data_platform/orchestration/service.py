"""Deterministic composition of the governed local pipeline stages."""

import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg

from sales_data_platform.config.settings import Settings
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.errors import IngestionError
from sales_data_platform.ingestion.service import ingest_source_file
from sales_data_platform.orchestration.history import (
    create_pipeline_execution,
    mark_pipeline_blocked,
    mark_pipeline_failed,
    mark_pipeline_running,
    mark_pipeline_succeeded,
    mark_stage_failed,
    mark_stage_running,
    mark_stage_skipped,
    mark_stage_succeeded,
    read_execution,
)
from sales_data_platform.orchestration.models import (
    FailureClassification,
    FailureDetail,
    PipelineExecutionId,
    PipelineResult,
    StageIdentity,
)
from sales_data_platform.quality.evaluation import evaluate_quality
from sales_data_platform.quality.expectations import (
    PRODUCT_SKU_UNIQUENESS,
    SALES_TRANSACTION_CURRENCY_CONSISTENCY,
)
from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationResult,
    QualityOutcomeStatus,
)
from sales_data_platform.transformation import mapping
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalSalesLine,
    TransformationBatchResult,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.service import transform_batch

logger = logging.getLogger(__name__)

_PRODUCT_V1 = SourceContractKey("northstar.product_catalog", 1)
_ECOMMERCE_V1 = SourceContractKey("northstar.ecommerce_sales", 1)
_RETAIL_V1 = SourceContractKey("northstar.retail_sales", 1)
_SUPPORTED_CONTRACTS = frozenset({_PRODUCT_V1, _ECOMMERCE_V1, _RETAIL_V1})
_UNSUCCESSFUL_TRANSFORMATION_STATUSES = frozenset(
    {
        TransformationOutcomeStatus.UNTRANSFORMABLE,
        TransformationOutcomeStatus.AMBIGUOUS,
        TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
    }
)


class _DQConfigurationError(Exception):
    """Identify coordinator-owned Data Quality construction failures."""


def _now() -> datetime:
    return datetime.now(UTC)


def _detail(classification: FailureClassification, code: str) -> FailureDetail:
    return FailureDetail(classification, code)


def _fail_pipeline(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    *,
    failed_stage: StageIdentity | None,
    skipped_stages: tuple[StageIdentity, ...],
    failure: FailureDetail,
) -> PipelineResult:
    if failed_stage is not None:
        mark_stage_failed(connection, execution_id, failed_stage, _now(), failure)
    for stage in skipped_stages:
        mark_stage_skipped(connection, execution_id, stage, _now())
    mark_pipeline_failed(connection, execution_id, _now(), failure)
    return read_execution(connection, execution_id)


def _evaluate_data_quality(
    contract_key: SourceContractKey, transformed: TransformationBatchResult
) -> tuple[QualityEvaluationResult, ...]:
    records = transformed.successful_records
    if contract_key == _PRODUCT_V1:
        if not all(isinstance(record, CanonicalProduct) for record in records):
            raise _DQConfigurationError("Invalid product transformation result")
        return (
            evaluate_quality(
                records,
                evaluated_scope_reference="product-catalog:v1",
                expectations=(PRODUCT_SKU_UNIQUENESS,),
            ),
        )

    if not all(isinstance(record, CanonicalSalesLine) for record in records):
        raise _DQConfigurationError("Invalid sales transformation result")
    groups: dict[tuple[str, str], list[CanonicalSalesLine]] = defaultdict(list)
    for record in records:
        groups[(record.sales_channel_code, record.source_transaction_number)].append(
            record
        )
    return tuple(
        evaluate_quality(
            groups[key],
            evaluated_scope_reference=f"sales-transaction:{key[0]}:{key[1]}",
            expectations=(SALES_TRANSACTION_CURRENCY_CONSISTENCY,),
        )
        for key in sorted(groups)
    )


def _quality_terminal_state(
    results: tuple[QualityEvaluationResult, ...],
) -> tuple[bool, bool]:
    if not all(isinstance(result, QualityEvaluationResult) for result in results):
        raise TypeError("Invalid Data Quality result")
    outcomes = tuple(outcome for result in results for outcome in result.outcomes)
    evaluation_error = any(
        outcome.status is QualityOutcomeStatus.EVALUATION_ERROR for outcome in outcomes
    )
    blocking = any(
        outcome.status is QualityOutcomeStatus.VIOLATED
        and outcome.disposition is QualityDisposition.BLOCKING
        for outcome in outcomes
    )
    return evaluation_error, blocking


def run_pipeline(
    connection: psycopg.Connection,
    *,
    contract_key: SourceContractKey,
    source_path: Path,
    settings: Settings,
    predecessor_execution_id: PipelineExecutionId | None = None,
) -> PipelineResult:
    """Execute one deterministic pipeline attempt and return durable history."""
    execution_id = PipelineExecutionId(uuid4())
    context = {"pipeline_execution_id": str(execution_id.value)}
    create_pipeline_execution(
        connection, execution_id, _now(), predecessor_execution_id
    )
    mark_pipeline_running(connection, execution_id, _now())

    if contract_key not in _SUPPORTED_CONTRACTS:
        failure = _detail(
            FailureClassification.CONFIGURATION_FAILURE, "CONFIGURATION_ERROR"
        )
        logger.warning(
            "Pipeline configuration rejected",
            extra={**context, "controlled_code": failure.code},
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=None,
            skipped_stages=tuple(StageIdentity),
            failure=failure,
        )

    mark_stage_running(connection, execution_id, StageIdentity.INGESTION, _now())
    try:
        batch = ingest_source_file(contract_key, source_path, settings=settings)
    except IngestionError:
        failure = _detail(FailureClassification.INGESTION_FAILURE, "INGESTION_ERROR")
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.INGESTION,
            skipped_stages=(StageIdentity.TRANSFORMATION, StageIdentity.DATA_QUALITY),
            failure=failure,
        )
    except Exception:
        failure = _detail(
            FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
            "UNEXPECTED_EXECUTION_ERROR",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.INGESTION,
            skipped_stages=(StageIdentity.TRANSFORMATION, StageIdentity.DATA_QUALITY),
            failure=failure,
        )
    mark_stage_succeeded(connection, execution_id, StageIdentity.INGESTION, _now())

    mark_stage_running(connection, execution_id, StageIdentity.TRANSFORMATION, _now())
    try:
        ruleset = TransformationRuleSetKey(contract_key, 1)
        transformed = transform_batch(batch, ruleset=ruleset)
        if not isinstance(transformed, TransformationBatchResult):
            failure = _detail(
                FailureClassification.INVALID_STAGE_RESULT, "INVALID_STAGE_RESULT"
            )
            return _fail_pipeline(
                connection,
                execution_id,
                failed_stage=StageIdentity.TRANSFORMATION,
                skipped_stages=(StageIdentity.DATA_QUALITY,),
                failure=failure,
            )
    except (ValueError, mapping.UnsupportedSourceContractError):
        failure = _detail(
            FailureClassification.CONFIGURATION_FAILURE, "CONFIGURATION_ERROR"
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.TRANSFORMATION,
            skipped_stages=(StageIdentity.DATA_QUALITY,),
            failure=failure,
        )
    except mapping.TransformationMappingError:
        failure = _detail(
            FailureClassification.TRANSFORMATION_FAILURE, "TRANSFORMATION_ERROR"
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.TRANSFORMATION,
            skipped_stages=(StageIdentity.DATA_QUALITY,),
            failure=failure,
        )
    except Exception:
        failure = _detail(
            FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
            "UNEXPECTED_EXECUTION_ERROR",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.TRANSFORMATION,
            skipped_stages=(StageIdentity.DATA_QUALITY,),
            failure=failure,
        )

    if any(
        outcome.status in _UNSUCCESSFUL_TRANSFORMATION_STATUSES
        for outcome in transformed.outcomes
    ):
        failure = _detail(
            FailureClassification.TRANSFORMATION_FAILURE,
            "TRANSFORMATION_UNSUCCESSFUL_OUTCOME",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.TRANSFORMATION,
            skipped_stages=(StageIdentity.DATA_QUALITY,),
            failure=failure,
        )
    mark_stage_succeeded(connection, execution_id, StageIdentity.TRANSFORMATION, _now())

    mark_stage_running(connection, execution_id, StageIdentity.DATA_QUALITY, _now())
    try:
        quality_results = _evaluate_data_quality(contract_key, transformed)
    except _DQConfigurationError:
        failure = _detail(
            FailureClassification.CONFIGURATION_FAILURE, "CONFIGURATION_ERROR"
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.DATA_QUALITY,
            skipped_stages=(),
            failure=failure,
        )
    except Exception:
        failure = _detail(
            FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
            "UNEXPECTED_EXECUTION_ERROR",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.DATA_QUALITY,
            skipped_stages=(),
            failure=failure,
        )
    try:
        evaluation_error, blocking = _quality_terminal_state(quality_results)
    except (TypeError, ValueError):
        failure = _detail(
            FailureClassification.INVALID_STAGE_RESULT, "INVALID_STAGE_RESULT"
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.DATA_QUALITY,
            skipped_stages=(),
            failure=failure,
        )
    except Exception:
        failure = _detail(
            FailureClassification.UNEXPECTED_EXECUTION_FAILURE,
            "UNEXPECTED_EXECUTION_ERROR",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.DATA_QUALITY,
            skipped_stages=(),
            failure=failure,
        )

    if evaluation_error:
        failure = _detail(
            FailureClassification.DATA_QUALITY_EVALUATION_FAILURE,
            "DATA_QUALITY_EVALUATION_ERROR",
        )
        return _fail_pipeline(
            connection,
            execution_id,
            failed_stage=StageIdentity.DATA_QUALITY,
            skipped_stages=(),
            failure=failure,
        )
    mark_stage_succeeded(connection, execution_id, StageIdentity.DATA_QUALITY, _now())
    if blocking:
        mark_pipeline_blocked(connection, execution_id, _now())
    else:
        mark_pipeline_succeeded(connection, execution_id, _now())
    return read_execution(connection, execution_id)
