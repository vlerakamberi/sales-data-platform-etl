"""Deterministic batch transformation over validated ingestion records."""

import logging

from sales_data_platform.ingestion.models import ValidatedBatch
from sales_data_platform.transformation import mapping
from sales_data_platform.transformation.models import (
    TransformationBatchResult,
    TransformationOutcome,
    TransformationOutcomeStatus,
    TransformationRuleSetKey,
)
from sales_data_platform.transformation.rules import TransformationRuleViolation

logger = logging.getLogger(__name__)

_SUPPORTED_CONTRACTS = frozenset(
    {
        mapping.PRODUCT_CATALOG_V1,
        mapping.ECOMMERCE_SALES_V1,
        mapping.RETAIL_SALES_V1,
    }
)


def transform_batch(
    batch: ValidatedBatch,
    *,
    ruleset: TransformationRuleSetKey,
) -> TransformationBatchResult:
    """Transform one coherent validated batch with exact outcome accounting."""

    if ruleset.source_contract_key != batch.contract_key:
        raise ValueError("Transformation ruleset does not match the batch contract")
    if batch.contract_key not in _SUPPORTED_CONTRACTS:
        raise mapping.UnsupportedSourceContractError(
            "Unsupported source contract for canonical transformation"
        )

    log_context = {
        "contract_id": batch.contract_key.source_contract_id,
        "contract_version": batch.contract_key.source_contract_version,
        "transformation_version": ruleset.transformation_version,
        "source_id": batch.source_id.value,
        "run_id": str(batch.run_id.value),
        "record_count": batch.record_count,
    }
    logger.info("Transformation started", extra=log_context)

    outcomes: list[TransformationOutcome] = []
    for record in batch.records:
        try:
            canonical_record = mapping.map_validated_record(
                batch.contract_key, record, ruleset
            )
        except mapping.UnsupportedSourceContractError:
            raise
        except TransformationRuleViolation:
            outcomes.append(
                TransformationOutcome(
                    status=TransformationOutcomeStatus.BUSINESS_RULE_REJECTED,
                    provenance=record.provenance,
                    ruleset=ruleset,
                    issue_code="BUSINESS_RULE_VIOLATION",
                    issue_message="Record violates governed transformation rules",
                )
            )
        except mapping.TransformationMappingError:
            outcomes.append(
                TransformationOutcome(
                    status=TransformationOutcomeStatus.UNTRANSFORMABLE,
                    provenance=record.provenance,
                    ruleset=ruleset,
                    issue_code="MAPPING_IMPOSSIBLE",
                    issue_message="Record cannot be deterministically transformed",
                )
            )
        else:
            outcomes.append(
                TransformationOutcome(
                    status=TransformationOutcomeStatus.SUCCESS,
                    provenance=record.provenance,
                    ruleset=ruleset,
                    canonical_record=canonical_record,
                )
            )

    result = TransformationBatchResult(
        source_contract_key=batch.contract_key,
        source_id=batch.source_id,
        run_id=batch.run_id,
        ruleset=ruleset,
        outcomes=tuple(outcomes),
    )
    completion_context = {
        **log_context,
        "success_count": result.success_count,
        "failure_count": result.failure_count,
    }
    if result.failure_count:
        logger.warning(
            "Transformation completed with unsuccessful outcomes",
            extra=completion_context,
        )
    else:
        logger.info("Transformation completed", extra=completion_context)
    return result
