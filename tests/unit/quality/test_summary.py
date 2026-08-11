"""Unit tests for deterministic Data Quality count summaries."""

from dataclasses import fields

from sales_data_platform.quality.models import (
    QualityDisposition,
    QualityEvaluationResult,
    QualityExpectationKey,
    QualityOutcome,
    QualityOutcomeStatus,
)
from sales_data_platform.quality.summary import QualitySummary, summarize_quality

KEY = QualityExpectationKey("TEST-EXPECTATION", 1)


def _outcome(
    status: QualityOutcomeStatus,
    disposition: QualityDisposition | None = None,
) -> QualityOutcome:
    return QualityOutcome(
        KEY,
        status,
        "scope:1",
        disposition=disposition,
        affected_scope_reference="scope:1" if disposition is not None else None,
    )


def test_empty_result_has_all_zero_counts() -> None:
    summary = summarize_quality(QualityEvaluationResult(()))
    assert summary == QualitySummary(0, 0, 0, 0, 0, 0, 0, 0)


def test_each_status_and_disposition_has_explicit_count_semantics() -> None:
    outcomes = (
        _outcome(QualityOutcomeStatus.SATISFIED),
        _outcome(QualityOutcomeStatus.VIOLATED, QualityDisposition.BLOCKING),
        _outcome(QualityOutcomeStatus.VIOLATED, QualityDisposition.NON_BLOCKING),
        _outcome(QualityOutcomeStatus.NOT_APPLICABLE),
        _outcome(QualityOutcomeStatus.EVALUATION_ERROR),
    )

    summary = summarize_quality(QualityEvaluationResult(outcomes))

    assert summary == QualitySummary(
        total_evaluation_count=5,
        applicable_evaluation_count=3,
        satisfied_count=1,
        violation_count=2,
        blocking_violation_count=1,
        non_blocking_violation_count=1,
        not_applicable_count=1,
        evaluation_error_count=1,
    )


def test_summary_invariants_and_repeated_determinism() -> None:
    result = QualityEvaluationResult(
        (
            _outcome(QualityOutcomeStatus.SATISFIED),
            _outcome(QualityOutcomeStatus.VIOLATED, QualityDisposition.BLOCKING),
            _outcome(QualityOutcomeStatus.NOT_APPLICABLE),
            _outcome(QualityOutcomeStatus.EVALUATION_ERROR),
        )
    )
    first = summarize_quality(result)
    second = summarize_quality(result)

    assert first == second
    assert first.total_evaluation_count == (
        first.satisfied_count
        + first.violation_count
        + first.not_applicable_count
        + first.evaluation_error_count
    )
    assert first.applicable_evaluation_count == (
        first.satisfied_count + first.violation_count
    )
    assert first.violation_count == (
        first.blocking_violation_count + first.non_blocking_violation_count
    )


def test_summary_has_no_rates_scores_population_or_operational_state() -> None:
    names = {field.name for field in fields(QualitySummary)}
    assert names == {
        "total_evaluation_count",
        "applicable_evaluation_count",
        "satisfied_count",
        "violation_count",
        "blocking_violation_count",
        "non_blocking_violation_count",
        "not_applicable_count",
        "evaluation_error_count",
    }
    assert "violation_rate" not in names
    assert "affected_population" not in names
    assert "quality_score" not in names
    assert "database_id" not in names
    assert "workflow_state" not in names
