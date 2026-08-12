"""Pure runtime metrics derived from authoritative orchestration results."""

from dataclasses import dataclass
from datetime import timedelta

from sales_data_platform.orchestration.models import (
    PipelineExecutionId,
    PipelineLifecycleState,
    PipelineResult,
    StageIdentity,
    StageLifecycleState,
)


@dataclass(frozen=True, slots=True)
class StageRuntimeMetrics:
    """Derived runtime information for one governed pipeline stage."""

    stage: StageIdentity
    state: StageLifecycleState
    duration: timedelta | None


@dataclass(frozen=True, slots=True)
class PipelineRuntimeMetrics:
    """Derived runtime information for one pipeline execution."""

    execution_id: PipelineExecutionId
    state: PipelineLifecycleState
    duration: timedelta | None
    stages: tuple[StageRuntimeMetrics, ...]


def derive_runtime_metrics(result: PipelineResult) -> PipelineRuntimeMetrics:
    """Derive immutable durations solely from persisted result timestamps."""
    duration = (
        result.completed_at - result.started_at
        if result.started_at is not None and result.completed_at is not None
        else None
    )
    stages = tuple(
        StageRuntimeMetrics(
            stage=stage.stage,
            state=stage.state,
            duration=stage.completed_at - stage.started_at
            if stage.started_at is not None and stage.completed_at is not None
            else None,
        )
        for stage in result.stages
    )
    return PipelineRuntimeMetrics(
        execution_id=result.execution_id,
        state=result.state,
        duration=duration,
        stages=stages,
    )
