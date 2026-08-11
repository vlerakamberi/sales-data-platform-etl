"""Immutable, persistence-neutral Data Quality domain contracts."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from sales_data_platform.ingestion.models import RecordProvenance


@dataclass(frozen=True, slots=True)
class QualityExpectationKey:
    """Stable identity of one governed expectation semantic version."""

    expectation_id: str
    expectation_version: int

    def __post_init__(self) -> None:
        _require_nonblank(self.expectation_id, "Expectation ID")
        if (
            not isinstance(self.expectation_version, int)
            or isinstance(self.expectation_version, bool)
            or self.expectation_version <= 0
        ):
            raise ValueError("Expectation version must be a positive integer")


class QualityDisposition(Enum):
    """The complete governed violation-disposition taxonomy."""

    BLOCKING = "BLOCKING"
    NON_BLOCKING = "NON_BLOCKING"


class QualityEvaluationScope(Enum):
    """The amount of governed data evaluated by an expectation."""

    RECORD = "RECORD"
    COLLECTION = "COLLECTION"
    GROUP = "GROUP"


class QualityOutcomeStatus(Enum):
    """The complete governed Data Quality outcome taxonomy."""

    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EVALUATION_ERROR = "EVALUATION_ERROR"


@dataclass(frozen=True, slots=True)
class QualityExpectationDefinition:
    """Governed metadata for one immutable business-quality expectation."""

    key: QualityExpectationKey
    description: str
    business_rationale: str
    canonical_scope: str
    evaluation_scope: QualityEvaluationScope
    violation_disposition: QualityDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.key, QualityExpectationKey):
            raise TypeError("Expectation key must be a QualityExpectationKey")
        _require_nonblank(self.description, "Expectation description")
        _require_nonblank(self.business_rationale, "Business rationale")
        _require_nonblank(self.canonical_scope, "Canonical scope")
        if not isinstance(self.evaluation_scope, QualityEvaluationScope):
            raise TypeError("Evaluation scope must be a QualityEvaluationScope")
        if not isinstance(self.violation_disposition, QualityDisposition):
            raise TypeError("Violation disposition must be a QualityDisposition")


type QualityEvidenceValue = str | int | bool | Decimal | None
_EVIDENCE_VALUE_TYPES = (str, int, bool, Decimal, type(None))


@dataclass(frozen=True, slots=True)
class QualityOutcome:
    """One normalized, traceable Data Quality result."""

    expectation_key: QualityExpectationKey
    status: QualityOutcomeStatus
    evaluated_scope_reference: str
    disposition: QualityDisposition | None = None
    affected_scope_reference: str | None = None
    provenance: tuple[RecordProvenance, ...] = ()
    evidence: Mapping[str, QualityEvidenceValue] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.expectation_key, QualityExpectationKey):
            raise TypeError("Expectation key must be a QualityExpectationKey")
        if not isinstance(self.status, QualityOutcomeStatus):
            raise TypeError("Outcome status must be a QualityOutcomeStatus")
        _require_nonblank(self.evaluated_scope_reference, "Evaluated scope reference")

        provenance = tuple(self.provenance)
        if not all(isinstance(item, RecordProvenance) for item in provenance):
            raise TypeError("Provenance references must be RecordProvenance values")
        object.__setattr__(self, "provenance", provenance)
        object.__setattr__(self, "evidence", _freeze_evidence(self.evidence))

        if self.status is QualityOutcomeStatus.VIOLATED:
            if not isinstance(self.disposition, QualityDisposition):
                raise ValueError("A violated outcome requires a governed disposition")
            _require_nonblank(
                self.affected_scope_reference,
                "A violated outcome affected scope reference",
            )
            return

        if self.disposition is not None:
            raise ValueError("Only a violated outcome may carry a disposition")
        if self.affected_scope_reference is not None:
            raise ValueError(
                "Only a violated outcome may carry an affected scope reference"
            )


@dataclass(frozen=True, slots=True)
class QualityEvaluationResult:
    """An immutable collection preserving supplied quality-outcome ordering."""

    outcomes: tuple[QualityOutcome, ...]

    def __post_init__(self) -> None:
        outcomes = tuple(self.outcomes)
        if not all(isinstance(item, QualityOutcome) for item in outcomes):
            raise TypeError("Evaluation results may contain only QualityOutcome values")
        object.__setattr__(self, "outcomes", outcomes)


def _require_nonblank(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


def _freeze_evidence(
    evidence: Mapping[str, QualityEvidenceValue],
) -> Mapping[str, QualityEvidenceValue]:
    if not isinstance(evidence, Mapping):
        raise TypeError("Quality evidence must be a mapping")

    frozen: dict[str, QualityEvidenceValue] = {}
    for key, value in evidence.items():
        _require_nonblank(key, "Evidence key")
        if not isinstance(value, _EVIDENCE_VALUE_TYPES):
            raise TypeError("Quality evidence contains an unsupported value")
        frozen[key] = value
    return MappingProxyType(frozen)
