"""Tests for immutable pipeline orchestration domain contracts."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from enum import Enum
from itertools import product
from uuid import UUID

import pytest

from sales_data_platform.orchestration.errors import (
    InvalidOrchestrationResultError,
)
from sales_data_platform.orchestration.models import (
    PIPELINE_LIFECYCLE_TRANSITIONS,
    PIPELINE_TERMINAL_STATES,
    STAGE_LIFECYCLE_TRANSITIONS,
    STAGE_TERMINAL_STATES,
    FailureClassification,
    FailureDetail,
    PipelineExecutionId,
    PipelineLifecycleState,
    PipelineResult,
    StageIdentity,
    StageLifecycleState,
    StageResult,
    is_terminal_pipeline_state,
    is_terminal_stage_state,
    is_valid_pipeline_transition,
    is_valid_stage_transition,
)

CREATED_AT = datetime(2026, 1, 1, 9, tzinfo=UTC)
STARTED_AT = CREATED_AT + timedelta(minutes=1)
COMPLETED_AT = STARTED_AT + timedelta(minutes=2)
EXECUTION_ID = PipelineExecutionId(UUID("11111111-1111-4111-8111-111111111111"))
PREDECESSOR_ID = PipelineExecutionId(UUID("22222222-2222-4222-8222-222222222222"))
FAILURE = FailureDetail(FailureClassification.INGESTION_FAILURE, "SOURCE_INVALID")


def test_pipeline_execution_id_is_uuid_backed_equal_hashable_and_immutable() -> None:
    value = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    execution_id = PipelineExecutionId(value)

    assert execution_id.value == value
    assert execution_id == PipelineExecutionId(value)
    assert execution_id != PipelineExecutionId(
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    )
    assert {execution_id, PipelineExecutionId(value)} == {execution_id}
    with pytest.raises(FrozenInstanceError):
        execution_id.value = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


def test_pipeline_execution_id_rejects_non_uuid() -> None:
    with pytest.raises(TypeError):
        PipelineExecutionId("not-a-uuid")  # type: ignore[arg-type]


def test_pipeline_lifecycle_is_exact_and_has_exact_terminal_states() -> None:
    assert [(state.name, state.value) for state in PipelineLifecycleState] == [
        ("PENDING", "PENDING"),
        ("RUNNING", "RUNNING"),
        ("SUCCEEDED", "SUCCEEDED"),
        ("BLOCKED", "BLOCKED"),
        ("FAILED", "FAILED"),
    ]
    assert PIPELINE_TERMINAL_STATES == {
        PipelineLifecycleState.SUCCEEDED,
        PipelineLifecycleState.BLOCKED,
        PipelineLifecycleState.FAILED,
    }
    assert {
        state for state in PipelineLifecycleState if is_terminal_pipeline_state(state)
    } == PIPELINE_TERMINAL_STATES


def test_stage_identity_is_exact_and_ordered() -> None:
    assert [(stage.name, stage.value) for stage in StageIdentity] == [
        ("INGESTION", 1),
        ("TRANSFORMATION", 2),
        ("DATA_QUALITY", 3),
    ]
    assert issubclass(StageIdentity, Enum)


def test_stage_lifecycle_is_exact_and_has_exact_terminal_states() -> None:
    assert [(state.name, state.value) for state in StageLifecycleState] == [
        ("PENDING", "PENDING"),
        ("RUNNING", "RUNNING"),
        ("SUCCEEDED", "SUCCEEDED"),
        ("FAILED", "FAILED"),
        ("SKIPPED", "SKIPPED"),
    ]
    assert STAGE_TERMINAL_STATES == {
        StageLifecycleState.SUCCEEDED,
        StageLifecycleState.FAILED,
        StageLifecycleState.SKIPPED,
    }
    assert {
        state for state in StageLifecycleState if is_terminal_stage_state(state)
    } == STAGE_TERMINAL_STATES


def test_failure_classification_is_exact() -> None:
    expected = [
        "INGESTION_FAILURE",
        "TRANSFORMATION_FAILURE",
        "DATA_QUALITY_EVALUATION_FAILURE",
        "INVALID_STAGE_RESULT",
        "PERSISTENCE_FAILURE",
        "CONFIGURATION_FAILURE",
        "UNEXPECTED_EXECUTION_FAILURE",
    ]
    assert [category.name for category in FailureClassification] == expected
    assert [category.value for category in FailureClassification] == expected


def test_failure_detail_is_bounded_and_immutable() -> None:
    detail = FailureDetail(FailureClassification.PERSISTENCE_FAILURE)
    coded = FailureDetail(
        FailureClassification.INVALID_STAGE_RESULT, "INVALID.RESULT-1"
    )

    assert detail.code is None
    assert coded.code == "INVALID.RESULT-1"
    assert [field.name for field in fields(FailureDetail)] == ["category", "code"]
    with pytest.raises(FrozenInstanceError):
        detail.code = "CHANGED"
    with pytest.raises(TypeError):
        FailureDetail("arbitrary")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        FailureDetail(FailureClassification.INGESTION_FAILURE, "unsafe message")


@pytest.mark.parametrize(
    ("state", "started_at", "completed_at", "failure"),
    [
        (StageLifecycleState.PENDING, None, None, None),
        (StageLifecycleState.RUNNING, STARTED_AT, None, None),
        (StageLifecycleState.SUCCEEDED, STARTED_AT, COMPLETED_AT, None),
        (StageLifecycleState.FAILED, STARTED_AT, COMPLETED_AT, FAILURE),
        (StageLifecycleState.SKIPPED, None, COMPLETED_AT, None),
    ],
)
def test_stage_result_accepts_each_valid_lifecycle_shape(
    state: StageLifecycleState,
    started_at: datetime | None,
    completed_at: datetime | None,
    failure: FailureDetail | None,
) -> None:
    result = StageResult(
        StageIdentity.INGESTION, state, started_at, completed_at, failure
    )

    assert result.state is state


@pytest.mark.parametrize(
    ("state", "started_at", "completed_at", "failure"),
    [
        (StageLifecycleState.PENDING, STARTED_AT, None, None),
        (StageLifecycleState.RUNNING, STARTED_AT, COMPLETED_AT, None),
        (StageLifecycleState.SUCCEEDED, None, None, None),
        (StageLifecycleState.SUCCEEDED, STARTED_AT, COMPLETED_AT, FAILURE),
        (StageLifecycleState.FAILED, STARTED_AT, COMPLETED_AT, None),
    ],
)
def test_stage_result_rejects_invalid_lifecycle_shapes(
    state: StageLifecycleState,
    started_at: datetime | None,
    completed_at: datetime | None,
    failure: FailureDetail | None,
) -> None:
    with pytest.raises(InvalidOrchestrationResultError):
        StageResult(StageIdentity.INGESTION, state, started_at, completed_at, failure)


def test_stage_result_rejects_completion_before_start_and_naive_datetime() -> None:
    with pytest.raises(InvalidOrchestrationResultError):
        StageResult(
            StageIdentity.INGESTION,
            StageLifecycleState.SUCCEEDED,
            COMPLETED_AT,
            STARTED_AT,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        StageResult(
            StageIdentity.INGESTION,
            StageLifecycleState.RUNNING,
            datetime(2026, 1, 1, 9),
        )


def _pipeline_result(
    state: PipelineLifecycleState,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    failure: FailureDetail | None = None,
    stages: tuple[StageResult, ...] = (),
    predecessor: PipelineExecutionId | None = None,
    created_at: datetime = CREATED_AT,
) -> PipelineResult:
    return PipelineResult(
        execution_id=EXECUTION_ID,
        state=state,
        stages=stages,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        predecessor_execution_id=predecessor,
        failure=failure,
    )


@pytest.mark.parametrize(
    ("state", "started_at", "completed_at", "failure"),
    [
        (PipelineLifecycleState.PENDING, None, None, None),
        (PipelineLifecycleState.RUNNING, STARTED_AT, None, None),
        (PipelineLifecycleState.SUCCEEDED, STARTED_AT, COMPLETED_AT, None),
        (PipelineLifecycleState.BLOCKED, STARTED_AT, COMPLETED_AT, None),
        (PipelineLifecycleState.FAILED, STARTED_AT, COMPLETED_AT, FAILURE),
    ],
)
def test_pipeline_result_accepts_each_valid_lifecycle_shape(
    state: PipelineLifecycleState,
    started_at: datetime | None,
    completed_at: datetime | None,
    failure: FailureDetail | None,
) -> None:
    result = _pipeline_result(
        state,
        started_at=started_at,
        completed_at=completed_at,
        failure=failure,
        predecessor=PREDECESSOR_ID,
    )

    assert result.state is state
    assert result.predecessor_execution_id == PREDECESSOR_ID


def test_pipeline_result_freezes_stage_collection_and_preserves_order() -> None:
    stages = [
        StageResult(StageIdentity.INGESTION, StageLifecycleState.PENDING),
        StageResult(StageIdentity.TRANSFORMATION, StageLifecycleState.PENDING),
        StageResult(StageIdentity.DATA_QUALITY, StageLifecycleState.PENDING),
    ]

    result = _pipeline_result(PipelineLifecycleState.PENDING, stages=stages)  # type: ignore[arg-type]

    assert isinstance(result.stages, tuple)
    assert tuple(stage.stage for stage in result.stages) == tuple(StageIdentity)
    with pytest.raises(FrozenInstanceError):
        result.stages = ()


def test_pipeline_result_rejects_duplicate_or_out_of_order_stages() -> None:
    ingestion = StageResult(StageIdentity.INGESTION, StageLifecycleState.PENDING)
    transformation = StageResult(
        StageIdentity.TRANSFORMATION, StageLifecycleState.PENDING
    )
    with pytest.raises(InvalidOrchestrationResultError, match="duplicate"):
        _pipeline_result(PipelineLifecycleState.PENDING, stages=(ingestion, ingestion))
    with pytest.raises(InvalidOrchestrationResultError, match="order"):
        _pipeline_result(
            PipelineLifecycleState.PENDING, stages=(transformation, ingestion)
        )


def test_pipeline_result_rejects_self_predecessor() -> None:
    with pytest.raises(InvalidOrchestrationResultError, match="itself"):
        _pipeline_result(PipelineLifecycleState.PENDING, predecessor=EXECUTION_ID)


@pytest.mark.parametrize(
    ("state", "started_at", "completed_at", "failure"),
    [
        (PipelineLifecycleState.SUCCEEDED, STARTED_AT, None, None),
        (PipelineLifecycleState.FAILED, STARTED_AT, COMPLETED_AT, None),
        (PipelineLifecycleState.SUCCEEDED, STARTED_AT, COMPLETED_AT, FAILURE),
        (PipelineLifecycleState.BLOCKED, STARTED_AT, COMPLETED_AT, FAILURE),
    ],
)
def test_pipeline_result_rejects_invalid_terminal_shapes(
    state: PipelineLifecycleState,
    started_at: datetime | None,
    completed_at: datetime | None,
    failure: FailureDetail | None,
) -> None:
    with pytest.raises(InvalidOrchestrationResultError):
        _pipeline_result(
            state,
            started_at=started_at,
            completed_at=completed_at,
            failure=failure,
        )


def test_pipeline_result_rejects_completion_before_start_and_naive_datetime() -> None:
    with pytest.raises(InvalidOrchestrationResultError):
        _pipeline_result(
            PipelineLifecycleState.SUCCEEDED,
            started_at=COMPLETED_AT,
            completed_at=STARTED_AT,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        _pipeline_result(
            PipelineLifecycleState.PENDING,
            created_at=datetime(2026, 1, 1, 9),
        )


def test_pipeline_transition_rules_accept_exactly_authorized_pairs() -> None:
    expected = {
        (PipelineLifecycleState.PENDING, PipelineLifecycleState.RUNNING),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.SUCCEEDED),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.BLOCKED),
        (PipelineLifecycleState.RUNNING, PipelineLifecycleState.FAILED),
    }

    assert PIPELINE_LIFECYCLE_TRANSITIONS == expected
    assert {
        pair
        for pair in product(PipelineLifecycleState, repeat=2)
        if is_valid_pipeline_transition(*pair)
    } == expected


def test_stage_transition_rules_accept_exactly_authorized_pairs() -> None:
    expected = {
        (StageLifecycleState.PENDING, StageLifecycleState.RUNNING),
        (StageLifecycleState.PENDING, StageLifecycleState.SKIPPED),
        (StageLifecycleState.RUNNING, StageLifecycleState.SUCCEEDED),
        (StageLifecycleState.RUNNING, StageLifecycleState.FAILED),
    }

    assert STAGE_LIFECYCLE_TRANSITIONS == expected
    assert {
        pair
        for pair in product(StageLifecycleState, repeat=2)
        if is_valid_stage_transition(*pair)
    } == expected
