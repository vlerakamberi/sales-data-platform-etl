"""Immutable, persistence-neutral transformation domain models."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.ingestion.models import (
    RecordProvenance,
    RunIdentity,
    SourceIdentity,
)


@dataclass(frozen=True, slots=True)
class TransformationRuleSetKey:
    """Identity of transformation semantics for one exact source contract."""

    source_contract_key: SourceContractKey
    transformation_version: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transformation_version, int)
            or isinstance(self.transformation_version, bool)
            or self.transformation_version <= 0
        ):
            raise ValueError("Transformation version must be a positive integer")


@dataclass(frozen=True, slots=True)
class CanonicalProduct:
    """A canonical Northstar product expressed without persistence identity."""

    sku: str
    product_name: str
    category_code: str
    list_price: Decimal | None
    unit_cost: Decimal | None
    product_currency_code: str | None
    provenance: RecordProvenance
    ruleset: TransformationRuleSetKey


class CustomerReferenceState(Enum):
    """The governed customer-reference states available during transformation."""

    ABSENT = "ABSENT"
    UNRESOLVED_SOURCE_REFERENCE = "UNRESOLVED_SOURCE_REFERENCE"


type _ContextScalar = str | int | bool | Decimal | datetime | date | None
_CONTEXT_SCALAR_TYPES = (str, int, bool, Decimal, datetime, date, type(None))


def _freeze_context_value(value: object) -> object:
    """Recursively freeze narrowly bounded source-local context values."""

    if isinstance(value, _CONTEXT_SCALAR_TYPES):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise TypeError("Source-local context mapping keys must be strings")
            frozen[key] = _freeze_context_value(nested_value)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_context_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_context_value(item) for item in value)
    raise TypeError("Source-local context contains an unsupported mutable value")


def _freeze_context(context: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze_context_value(context)
    if not isinstance(frozen, Mapping):  # pragma: no cover - constrained by signature
        raise TypeError("Source-local context must be a mapping")
    return frozen


@dataclass(frozen=True, slots=True)
class CanonicalSalesLine:
    """A canonical Northstar sales line without database surrogate identities."""

    sales_channel_code: str
    source_transaction_number: str
    transaction_timestamp: datetime
    store_code: str | None
    customer_reference_state: CustomerReferenceState
    product_sku: str
    quantity: int
    unit_price: Decimal
    currency_code: str
    line_amount: Decimal
    source_local_context: Mapping[str, object]
    provenance: RecordProvenance
    ruleset: TransformationRuleSetKey

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_local_context", _freeze_context(self.source_local_context)
        )


class TransformationOutcomeStatus(Enum):
    """The complete governed transformation outcome taxonomy."""

    SUCCESS = "SUCCESS"
    UNTRANSFORMABLE = "UNTRANSFORMABLE"
    AMBIGUOUS = "AMBIGUOUS"
    BUSINESS_RULE_REJECTED = "BUSINESS_RULE_REJECTED"


type CanonicalRecord = CanonicalProduct | CanonicalSalesLine


@dataclass(frozen=True, slots=True)
class TransformationOutcome:
    """The explicit result of attempting to transform one validated record."""

    status: TransformationOutcomeStatus
    provenance: RecordProvenance
    ruleset: TransformationRuleSetKey
    canonical_record: CanonicalRecord | None = None
    issue_code: str | None = None
    issue_message: str | None = None

    def __post_init__(self) -> None:
        if self.status is TransformationOutcomeStatus.SUCCESS:
            if self.canonical_record is None:
                raise ValueError("A successful outcome requires a canonical record")
            if self.issue_code is not None or self.issue_message is not None:
                raise ValueError("A successful outcome cannot contain failure details")
            return

        if self.canonical_record is not None:
            raise ValueError(
                "An unsuccessful outcome cannot contain a canonical record"
            )
        if not _is_safe_issue_text(self.issue_code) or not _is_safe_issue_text(
            self.issue_message
        ):
            raise ValueError(
                "An unsuccessful outcome requires an issue code and message"
            )


def _is_safe_issue_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, slots=True)
class TransformationBatchResult:
    """Ordered transformation outcomes for one validated source batch."""

    source_contract_key: SourceContractKey
    source_id: SourceIdentity
    run_id: RunIdentity
    ruleset: TransformationRuleSetKey
    outcomes: tuple[TransformationOutcome, ...]

    def __post_init__(self) -> None:
        outcomes = tuple(self.outcomes)
        if self.ruleset.source_contract_key != self.source_contract_key:
            raise ValueError("Batch and ruleset source contract identities must match")
        for outcome in outcomes:
            if outcome.ruleset != self.ruleset:
                raise ValueError("Batch and outcome rulesets must match")
            if outcome.provenance.contract_key != self.source_contract_key:
                raise ValueError("Batch and outcome source contracts must match")
            if outcome.provenance.source_id != self.source_id:
                raise ValueError("Batch and outcome source identities must match")
            if outcome.provenance.run_id != self.run_id:
                raise ValueError("Batch and outcome run identities must match")
        object.__setattr__(self, "outcomes", outcomes)

    @property
    def record_count(self) -> int:
        """Return the number of attempted validated records."""

        return len(self.outcomes)

    @property
    def success_count(self) -> int:
        """Return the number of successful outcomes."""

        return sum(
            outcome.status is TransformationOutcomeStatus.SUCCESS
            for outcome in self.outcomes
        )

    @property
    def failure_count(self) -> int:
        """Return the number of unsuccessful outcomes."""

        return self.record_count - self.success_count

    @property
    def successful_records(self) -> tuple[CanonicalRecord, ...]:
        """Return canonical records from successful outcomes in source order."""

        return tuple(
            outcome.canonical_record
            for outcome in self.outcomes
            if outcome.status is TransformationOutcomeStatus.SUCCESS
            and outcome.canonical_record is not None
        )
