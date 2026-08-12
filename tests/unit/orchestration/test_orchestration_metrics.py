"""Unit tests for pure orchestration runtime-metrics derivation."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from sales_data_platform.orchestration.metrics import (
    PipelineRuntimeMetrics,
    StageRuntimeMetrics,
    derive_runtime_metrics,
)
from sales_data_platform.orchestration.models import (
    FailureClassification,
    FailureDetail,
    PipelineExecutionId,
    PipelineLifecycleState,
    PipelineResult,
    StageIdentity,
    StageLifecycleState,
    StageResult,
)

CREATED = datetime(2026, 8, 12, 8, 59, tzinfo=UTC)
STARTED = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)
COMPLETED = datetime(2026, 8, 12, 9, 7, 30, tzinfo=UTC)
EXECUTION_ID = PipelineExecutionId(UUID("3516dbe2-141a-43e8-b346-0861fb72d92f"))
FAILURE = FailureDetail(
    FailureClassification.INGESTION_FAILURE,
    "INGESTION_ERROR",
)


def _stage(
    stage: StageIdentity,
    state: StageLifecycleState,
    *,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> StageResult:
    return StageResult(
        stage=stage,
        state=state,
        started_at=started_at,
        completed_at=completed_at,
        failure=FAILURE if state is StageLifecycleState.FAILED else None,
    )


def _pipeline(
    state: PipelineLifecycleState,
    *,
    stages: tuple[StageResult, ...] = (),
) -> PipelineResult:
    started_at = None if state is PipelineLifecycleState.PENDING else STARTED
    completed_at = (
        COMPLETED
        if state
        in {
            PipelineLifecycleState.SUCCEEDED,
            PipelineLifecycleState.BLOCKED,
            PipelineLifecycleState.FAILED,
        }
        else None
    )
    return PipelineResult(
        execution_id=EXECUTION_ID,
        state=state,
        stages=stages,
        created_at=CREATED,
        started_at=started_at,
        completed_at=completed_at,
        failure=FAILURE if state is PipelineLifecycleState.FAILED else None,
    )


@pytest.mark.parametrize(
    "state",
    [
        PipelineLifecycleState.SUCCEEDED,
        PipelineLifecycleState.BLOCKED,
        PipelineLifecycleState.FAILED,
    ],
)
def test_completed_pipeline_states_have_exact_duration(state) -> None:
    metrics = derive_runtime_metrics(_pipeline(state))

    assert metrics.duration == timedelta(minutes=7, seconds=30)
    assert metrics.execution_id == EXECUTION_ID
    assert metrics.state is state


@pytest.mark.parametrize(
    "state",
    [PipelineLifecycleState.PENDING, PipelineLifecycleState.RUNNING],
)
def test_incomplete_pipeline_states_have_no_duration(state) -> None:
    assert derive_runtime_metrics(_pipeline(state)).duration is None


@pytest.mark.parametrize(
    "state",
    [StageLifecycleState.SUCCEEDED, StageLifecycleState.FAILED],
)
def test_completed_stage_states_have_exact_duration(state) -> None:
    source = _pipeline(
        PipelineLifecycleState.FAILED
        if state is StageLifecycleState.FAILED
        else PipelineLifecycleState.SUCCEEDED,
        stages=(
            _stage(
                StageIdentity.INGESTION,
                state,
                started_at=STARTED,
                completed_at=COMPLETED,
            ),
        ),
    )

    stage_metrics = derive_runtime_metrics(source).stages[0]

    assert stage_metrics.duration == timedelta(minutes=7, seconds=30)
    assert stage_metrics.stage is StageIdentity.INGESTION
    assert stage_metrics.state is state


@pytest.mark.parametrize(
    ("state", "started_at", "completed_at"),
    [
        (StageLifecycleState.PENDING, None, None),
        (StageLifecycleState.RUNNING, STARTED, None),
        (StageLifecycleState.SKIPPED, None, COMPLETED),
    ],
)
def test_incomplete_or_skipped_stage_has_no_duration(
    state, started_at, completed_at
) -> None:
    source = _pipeline(
        PipelineLifecycleState.RUNNING,
        stages=(
            _stage(
                StageIdentity.INGESTION,
                state,
                started_at=started_at,
                completed_at=completed_at,
            ),
        ),
    )

    assert derive_runtime_metrics(source).stages[0].duration is None


def test_partial_progress_preserves_stage_order_identity_state_and_durations() -> None:
    completed = STARTED + timedelta(seconds=45)
    stages = (
        _stage(
            StageIdentity.INGESTION,
            StageLifecycleState.SUCCEEDED,
            started_at=STARTED,
            completed_at=completed,
        ),
        _stage(
            StageIdentity.TRANSFORMATION,
            StageLifecycleState.RUNNING,
            started_at=completed,
        ),
        _stage(StageIdentity.DATA_QUALITY, StageLifecycleState.PENDING),
    )
    source = _pipeline(PipelineLifecycleState.RUNNING, stages=stages)

    metrics = derive_runtime_metrics(source)

    assert metrics.stages == (
        StageRuntimeMetrics(
            StageIdentity.INGESTION,
            StageLifecycleState.SUCCEEDED,
            timedelta(seconds=45),
        ),
        StageRuntimeMetrics(
            StageIdentity.TRANSFORMATION,
            StageLifecycleState.RUNNING,
            None,
        ),
        StageRuntimeMetrics(
            StageIdentity.DATA_QUALITY,
            StageLifecycleState.PENDING,
            None,
        ),
    )


def test_metrics_are_immutable_and_stages_are_an_immutable_tuple() -> None:
    metrics = derive_runtime_metrics(
        _pipeline(
            PipelineLifecycleState.SUCCEEDED,
            stages=(
                _stage(
                    StageIdentity.INGESTION,
                    StageLifecycleState.SUCCEEDED,
                    started_at=STARTED,
                    completed_at=COMPLETED,
                ),
            ),
        )
    )

    assert isinstance(metrics, PipelineRuntimeMetrics)
    assert isinstance(metrics.stages, tuple)
    with pytest.raises(FrozenInstanceError):
        metrics.duration = None
    with pytest.raises(FrozenInstanceError):
        metrics.stages[0].duration = None
    with pytest.raises(TypeError):
        metrics.stages[0] = metrics.stages[0]


def test_derivation_is_repeatable_and_does_not_mutate_source_or_use_current_time() -> (
    None
):
    source = _pipeline(
        PipelineLifecycleState.SUCCEEDED,
        stages=(
            _stage(
                StageIdentity.INGESTION,
                StageLifecycleState.SUCCEEDED,
                started_at=STARTED,
                completed_at=COMPLETED,
            ),
        ),
    )
    original = source

    first = derive_runtime_metrics(source)
    second = derive_runtime_metrics(source)

    assert first == second
    assert source == original
    assert source.started_at is STARTED
    assert source.completed_at is COMPLETED
    assert first.duration == COMPLETED - STARTED
