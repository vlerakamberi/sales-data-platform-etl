"""Deterministic count summary for structured Data Quality outcomes."""

from dataclasses import dataclass

from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationResult,
    QualityOutcomeStatus,
)


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Explicit counts derived only from structured quality outcomes."""

    total_evaluation_count: int
    applicable_evaluation_count: int
    satisfied_count: int
    violation_count: int
    blocking_violation_count: int
    non_blocking_violation_count: int
    not_applicable_count: int
    evaluation_error_count: int


def summarize_quality(result: QualityEvaluationResult) -> QualitySummary:
    """Summarize one immutable evaluation result without rates or scoring."""

    if not isinstance(result, QualityEvaluationResult):
        raise TypeError("Quality summary requires a QualityEvaluationResult")

    satisfied_count = sum(
        outcome.status is QualityOutcomeStatus.SATISFIED for outcome in result.outcomes
    )
    violation_count = sum(
        outcome.status is QualityOutcomeStatus.VIOLATED for outcome in result.outcomes
    )
    blocking_violation_count = sum(
        outcome.status is QualityOutcomeStatus.VIOLATED
        and outcome.disposition is QualityDisposition.BLOCKING
        for outcome in result.outcomes
    )
    non_blocking_violation_count = sum(
        outcome.status is QualityOutcomeStatus.VIOLATED
        and outcome.disposition is QualityDisposition.NON_BLOCKING
        for outcome in result.outcomes
    )
    not_applicable_count = sum(
        outcome.status is QualityOutcomeStatus.NOT_APPLICABLE
        for outcome in result.outcomes
    )
    evaluation_error_count = sum(
        outcome.status is QualityOutcomeStatus.EVALUATION_ERROR
        for outcome in result.outcomes
    )

    return QualitySummary(
        total_evaluation_count=len(result.outcomes),
        applicable_evaluation_count=satisfied_count + violation_count,
        satisfied_count=satisfied_count,
        violation_count=violation_count,
        blocking_violation_count=blocking_violation_count,
        non_blocking_violation_count=non_blocking_violation_count,
        not_applicable_count=not_applicable_count,
        evaluation_error_count=evaluation_error_count,
    )
