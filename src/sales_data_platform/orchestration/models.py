"""Immutable, persistence-neutral pipeline orchestration domain contracts."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from uuid import UUID

from sales_data_platform.orchestration.errors import (
    InvalidOrchestrationResultError,
)

_FAILURE_CODE_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9_.-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class PipelineExecutionId:
    """A supplied identity for one immutable pipeline execution attempt."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("Pipeline execution ID must be a UUID")


class PipelineLifecycleState(Enum):
    """The complete governed pipeline lifecycle."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


PIPELINE_TERMINAL_STATES = frozenset(
    {
        PipelineLifecycleState.SUCCEEDED,
        PipelineLifecycleState.BLOCKED,
        PipelineLifecycleState.FAILED,
    }
)


class StageIdentity(IntEnum):
    """The fixed pipeline stages in governed execution order."""

    INGESTION = 1
    TRANSFORMATION = 2
    DATA_QUALITY = 3


class StageLifecycleState(Enum):
    """The complete governed stage lifecycle."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


STAGE_TERMINAL_STATES = frozenset(
    {
        StageLifecycleState.SUCCEEDED,
        StageLifecycleState.FAILED,
        StageLifecycleState.SKIPPED,
    }
)


class FailureClassification(Enum):
    """The complete governed orchestration failure taxonomy."""

    INGESTION_FAILURE = "INGESTION_FAILURE"
    TRANSFORMATION_FAILURE = "TRANSFORMATION_FAILURE"
    DATA_QUALITY_EVALUATION_FAILURE = "DATA_QUALITY_EVALUATION_FAILURE"
    INVALID_STAGE_RESULT = "INVALID_STAGE_RESULT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    UNEXPECTED_EXECUTION_FAILURE = "UNEXPECTED_EXECUTION_FAILURE"


@dataclass(frozen=True, slots=True)
class FailureDetail:
    """A bounded, safe orchestration failure description."""

    category: FailureClassification
    code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, FailureClassification):
            raise TypeError("Failure category must be a FailureClassification")
        if self.code is not None and (
            not isinstance(self.code, str)
            or not _FAILURE_CODE_PATTERN.fullmatch(self.code)
        ):
            raise ValueError(
                "Failure code must be 1-64 uppercase letters, digits, dots, "
                "hyphens, or underscores"
            )


@dataclass(frozen=True, slots=True)
class StageResult:
    """The immutable lifecycle result for one governed pipeline stage."""

    stage: StageIdentity
    state: StageLifecycleState
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stage, StageIdentity):
            raise TypeError("Stage must be a StageIdentity")
        if not isinstance(self.state, StageLifecycleState):
            raise TypeError("Stage state must be a StageLifecycleState")
        _validate_optional_timestamp(self.started_at, "Stage start timestamp")
        _validate_optional_timestamp(self.completed_at, "Stage completion timestamp")
        _validate_timestamp_order(self.started_at, self.completed_at, "Stage")
        if self.failure is not None and not isinstance(self.failure, FailureDetail):
            raise TypeError("Stage failure must be a FailureDetail")

        valid_shape = {
            StageLifecycleState.PENDING: (
                self.started_at is None
                and self.completed_at is None
                and self.failure is None
            ),
            StageLifecycleState.RUNNING: (
                self.started_at is not None
                and self.completed_at is None
                and self.failure is None
            ),
            StageLifecycleState.SUCCEEDED: (
                self.started_at is not None
                and self.completed_at is not None
                and self.failure is None
            ),
            StageLifecycleState.FAILED: (
                self.started_at is not None
                and self.completed_at is not None
                and self.failure is not None
            ),
            StageLifecycleState.SKIPPED: (
                self.started_at is None
                and self.completed_at is not None
                and self.failure is None
            ),
        }[self.state]
        if not valid_shape:
            raise InvalidOrchestrationResultError(
                f"Invalid field combination for {self.state.value} stage result"
            )


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """The immutable lifecycle result for one pipeline execution attempt."""

    execution_id: PipelineExecutionId
    state: PipelineLifecycleState
    stages: tuple[StageResult, ...]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    predecessor_execution_id: PipelineExecutionId | None = None
    failure: FailureDetail | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.execution_id, PipelineExecutionId):
            raise TypeError("Execution ID must be a PipelineExecutionId")
        if not isinstance(self.state, PipelineLifecycleState):
            raise TypeError("Pipeline state must be a PipelineLifecycleState")
        _validate_timestamp(self.created_at, "Pipeline creation timestamp")
        _validate_optional_timestamp(self.started_at, "Pipeline start timestamp")
        _validate_optional_timestamp(self.completed_at, "Pipeline completion timestamp")
        _validate_timestamp_order(self.started_at, self.completed_at, "Pipeline")
        if self.predecessor_execution_id is not None and not isinstance(
            self.predecessor_execution_id, PipelineExecutionId
        ):
            raise TypeError("Predecessor execution ID must be a PipelineExecutionId")
        if self.failure is not None and not isinstance(self.failure, FailureDetail):
            raise TypeError("Pipeline failure must be a FailureDetail")

        stages = tuple(self.stages)
        if not all(isinstance(stage, StageResult) for stage in stages):
            raise TypeError("Pipeline stages must contain only StageResult values")
        object.__setattr__(self, "stages", stages)
        stage_identities = tuple(stage.stage for stage in stages)
        if len(set(stage_identities)) != len(stage_identities):
            raise InvalidOrchestrationResultError(
                "Pipeline result cannot contain duplicate stage identities"
            )
        if stage_identities != tuple(sorted(stage_identities)):
            raise InvalidOrchestrationResultError(
                "Pipeline stages must follow governed execution order"
            )
        if self.predecessor_execution_id == self.execution_id:
            raise InvalidOrchestrationResultError(
                "Pipeline execution cannot reference itself as predecessor"
            )

        if self.state is PipelineLifecycleState.PENDING and not (
            self.started_at is None
            and self.completed_at is None
            and self.failure is None
        ):
            raise InvalidOrchestrationResultError(
                "A PENDING pipeline cannot be started, completed, or failed"
            )
        if self.state is PipelineLifecycleState.RUNNING and not (
            self.started_at is not None
            and self.completed_at is None
            and self.failure is None
        ):
            raise InvalidOrchestrationResultError(
                "A RUNNING pipeline requires a start and cannot be completed or failed"
            )
        if self.state in PIPELINE_TERMINAL_STATES and self.completed_at is None:
            raise InvalidOrchestrationResultError(
                "A terminal pipeline requires a completion timestamp"
            )
        if self.state is PipelineLifecycleState.FAILED and self.failure is None:
            raise InvalidOrchestrationResultError(
                "A FAILED pipeline requires failure detail"
            )
        if (
            self.state
            in {
                PipelineLifecycleState.SUCCEEDED,
                PipelineLifecycleState.BLOCKED,
            }
            and self.failure is not None
        ):
            raise InvalidOrchestrationResultError(
                f"A {self.state.value} pipeline cannot carry failure detail"
            )


PIPELINE_LIFECYCLE_TRANSITIONS = frozenset(
    {
        (PipelineLifecycleState.PENDING, PipelineLifecycleState.RUNNING),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.SUCCEEDED),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.BLOCKED),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.FAILED),
    }
)

STAGE_LIFECYCLE_TRANSITIONS = frozenset(
    {
        (StageLifecycleState.PENDING, StageLifecycleState.RUNNING),
        (StageLifecycleState.PENDING, StageLifecycleState.SKIPPED),
        (StageLifecycleState.RUNNING, StageLifecycleState.SUCCEEDED),
        (StageLifecycleState.RUNNING, StageLifecycleState.FAILED),
    }
)


def is_terminal_pipeline_state(state: PipelineLifecycleState) -> bool:
    """Return whether a pipeline state is terminal."""

    return state in PIPELINE_TERMINAL_STATES


def is_terminal_stage_state(state: StageLifecycleState) -> bool:
    """Return whether a stage state is terminal."""

    return state in STAGE_TERMINAL_STATES


def is_valid_pipeline_transition(
    current: PipelineLifecycleState, target: PipelineLifecycleState
) -> bool:
    """Return whether a pipeline lifecycle transition is governed as legal."""

    return (current, target) in PIPELINE_LIFECYCLE_TRANSITIONS


def is_valid_stage_transition(
    current: StageLifecycleState, target: StageLifecycleState
) -> bool:
    """Return whether a stage lifecycle transition is governed as legal."""

    return (current, target) in STAGE_LIFECYCLE_TRANSITIONS


def _validate_timestamp(value: object, label: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _validate_optional_timestamp(value: object, label: str) -> None:
    if value is not None:
        _validate_timestamp(value, label)


def _validate_timestamp_order(
    started_at: datetime | None, completed_at: datetime | None, label: str
) -> None:
    if (
        started_at is not None
        and completed_at is not None
        and completed_at < started_at
    ):
        raise InvalidOrchestrationResultError(
            f"{label} completion cannot precede its start"
        )
