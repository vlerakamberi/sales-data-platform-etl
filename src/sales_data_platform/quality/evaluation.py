"""Deterministic evaluation mechanics for explicitly supplied expectations."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sales_data_platform.ingestion.models import RecordProvenance
from sales_data_platform.quality.models import (
    QualityEvaluationResult,
    QualityEvaluationScope,
    QualityEvidenceValue,
    QualityExpectationDefinition,
    QualityOutcome,
    QualityOutcomeStatus,
)
from sales_data_platform.transformation.models import (
    CanonicalProduct,
    CanonicalRecord,
    CanonicalSalesLine,
)

_CANONICAL_RECORD_TYPES = (CanonicalProduct, CanonicalSalesLine)

type CanonicalQualityScope = CanonicalRecord | tuple[CanonicalRecord, ...]
type ApplicabilityBehavior = Callable[[CanonicalQualityScope], bool]
type QualityConditionBehavior = Callable[
    [CanonicalQualityScope], "QualityConditionDecision"
]


class QualityEvaluationUnavailable(Exception):
    """A known inability to complete a required quality evaluation safely."""

    def __init__(self, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("Evaluation error reason code must be non-empty")
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class QualityConditionDecision:
    """The explicit business result returned by quality-condition behavior."""

    satisfied: bool
    affected_scope_reference: str | None = None
    provenance: tuple[RecordProvenance, ...] = ()
    evidence: Mapping[str, QualityEvidenceValue] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.satisfied, bool):
            raise TypeError("Condition decision must use a Boolean satisfied value")
        if self.satisfied and self.affected_scope_reference is not None:
            raise ValueError("A satisfied decision cannot identify an affected scope")
        if not self.satisfied and (
            not isinstance(self.affected_scope_reference, str)
            or not self.affected_scope_reference.strip()
        ):
            raise ValueError("A violated decision requires an affected scope reference")

        provenance = tuple(self.provenance)
        if not all(isinstance(item, RecordProvenance) for item in provenance):
            raise TypeError("Decision provenance must use RecordProvenance values")
        object.__setattr__(self, "provenance", provenance)

        evidence = dict(self.evidence)
        # QualityOutcome is the authority that validates evidence keys and values.
        object.__setattr__(self, "evidence", MappingProxyType(evidence))


@dataclass(frozen=True, slots=True)
class QualityExpectationExecution:
    """One explicitly supplied expectation and its deterministic behaviors."""

    definition: QualityExpectationDefinition
    applicability: ApplicabilityBehavior
    condition: QualityConditionBehavior

    def __post_init__(self) -> None:
        if not isinstance(self.definition, QualityExpectationDefinition):
            raise TypeError("Execution definition must be a quality expectation")
        if not callable(self.applicability):
            raise TypeError("Applicability behavior must be callable")
        if not callable(self.condition):
            raise TypeError("Quality-condition behavior must be callable")


def evaluate_quality(
    canonical_scope: CanonicalRecord | Iterable[CanonicalRecord],
    *,
    evaluated_scope_reference: str,
    expectations: Iterable[QualityExpectationExecution],
) -> QualityEvaluationResult:
    """Evaluate explicitly ordered expectations over one governed canonical scope."""

    if (
        not isinstance(evaluated_scope_reference, str)
        or not evaluated_scope_reference.strip()
    ):
        raise ValueError("Evaluated scope reference must be a non-empty string")

    scope = _normalize_canonical_scope(canonical_scope)
    executions = tuple(expectations)
    if not all(isinstance(item, QualityExpectationExecution) for item in executions):
        raise TypeError("Expectations must be QualityExpectationExecution values")

    outcomes: list[QualityOutcome] = []
    for execution in executions:
        _validate_scope(execution.definition.evaluation_scope, scope)
        default_provenance = _record_provenance(scope)

        try:
            applies = execution.applicability(scope)
            if not isinstance(applies, bool):
                raise TypeError("Applicability behavior must return a Boolean")
            if not applies:
                outcomes.append(
                    QualityOutcome(
                        expectation_key=execution.definition.key,
                        status=QualityOutcomeStatus.NOT_APPLICABLE,
                        evaluated_scope_reference=evaluated_scope_reference,
                        provenance=default_provenance,
                    )
                )
                continue

            decision = execution.condition(scope)
            if not isinstance(decision, QualityConditionDecision):
                raise TypeError(
                    "Quality-condition behavior must return QualityConditionDecision"
                )
        except QualityEvaluationUnavailable as error:
            outcomes.append(
                QualityOutcome(
                    expectation_key=execution.definition.key,
                    status=QualityOutcomeStatus.EVALUATION_ERROR,
                    evaluated_scope_reference=evaluated_scope_reference,
                    provenance=default_provenance,
                    evidence={"reason_code": error.reason_code},
                )
            )
            continue

        provenance = decision.provenance or default_provenance
        if decision.satisfied:
            outcomes.append(
                QualityOutcome(
                    expectation_key=execution.definition.key,
                    status=QualityOutcomeStatus.SATISFIED,
                    evaluated_scope_reference=evaluated_scope_reference,
                    provenance=provenance,
                    evidence=decision.evidence,
                )
            )
        else:
            outcomes.append(
                QualityOutcome(
                    expectation_key=execution.definition.key,
                    status=QualityOutcomeStatus.VIOLATED,
                    evaluated_scope_reference=evaluated_scope_reference,
                    disposition=execution.definition.violation_disposition,
                    affected_scope_reference=decision.affected_scope_reference,
                    provenance=provenance,
                    evidence=decision.evidence,
                )
            )

    return QualityEvaluationResult(tuple(outcomes))


def _normalize_canonical_scope(
    canonical_scope: CanonicalRecord | Iterable[CanonicalRecord],
) -> CanonicalQualityScope:
    if isinstance(canonical_scope, _CANONICAL_RECORD_TYPES):
        return canonical_scope
    try:
        records = tuple(canonical_scope)
    except TypeError as error:
        raise TypeError("Canonical scope must contain canonical records") from error
    if not all(isinstance(record, _CANONICAL_RECORD_TYPES) for record in records):
        raise TypeError("Canonical scope must contain only canonical records")
    return records


def _validate_scope(
    evaluation_scope: QualityEvaluationScope,
    canonical_scope: CanonicalQualityScope,
) -> None:
    is_record = isinstance(canonical_scope, _CANONICAL_RECORD_TYPES)
    if evaluation_scope is QualityEvaluationScope.RECORD and not is_record:
        raise ValueError("RECORD evaluation requires one canonical record")
    if evaluation_scope is not QualityEvaluationScope.RECORD and is_record:
        raise ValueError("COLLECTION and GROUP evaluation require a record sequence")


def _record_provenance(
    canonical_scope: CanonicalQualityScope,
) -> tuple[RecordProvenance, ...]:
    if isinstance(canonical_scope, _CANONICAL_RECORD_TYPES):
        return (canonical_scope.provenance,)
    return ()
