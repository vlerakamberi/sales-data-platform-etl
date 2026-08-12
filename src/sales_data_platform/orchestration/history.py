"""Durable PostgreSQL persistence for governed pipeline execution history."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import psycopg

from sales_data_platform.orchestration.errors import (
    InvalidLifecycleTransitionError,
    InvalidOrchestrationResultError,
    OrchestrationPersistenceError,
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

if TYPE_CHECKING:
    from collections.abc import Sequence


_PIPELINE_SELECT = """
    SELECT pipeline_execution_id, predecessor_execution_id, state, created_at,
           started_at, completed_at, failure_category, failure_code
    FROM pipeline_executions
    WHERE pipeline_execution_id = %s
"""
_STAGES_SELECT = """
    SELECT stage, state, started_at, completed_at,
           failure_category, failure_code
    FROM pipeline_stage_executions
    WHERE pipeline_execution_id = %s
    ORDER BY stage_sequence
"""


def _failure(category: str | None, code: str | None) -> FailureDetail | None:
    if category is None:
        return None
    return FailureDetail(FailureClassification(category), code)


def _reconstruct(
    pipeline_row: Sequence[object], stage_rows: Sequence[Sequence[object]]
) -> PipelineResult:
    try:
        stages = tuple(
            StageResult(
                stage=StageIdentity[stage],
                state=StageLifecycleState(state),
                started_at=started_at,
                completed_at=completed_at,
                failure=_failure(failure_category, failure_code),
            )
            for (
                stage,
                state,
                started_at,
                completed_at,
                failure_category,
                failure_code,
            ) in stage_rows
        )
        (
            execution_id,
            predecessor_execution_id,
            state,
            created_at,
            started_at,
            completed_at,
            failure_category,
            failure_code,
        ) = pipeline_row
        return PipelineResult(
            execution_id=PipelineExecutionId(execution_id),
            predecessor_execution_id=(
                PipelineExecutionId(predecessor_execution_id)
                if predecessor_execution_id is not None
                else None
            ),
            state=PipelineLifecycleState(state),
            stages=stages,
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            failure=_failure(failure_category, failure_code),
        )
    except InvalidOrchestrationResultError:
        raise
    except (TypeError, ValueError, KeyError) as error:
        raise InvalidOrchestrationResultError(
            "Persisted orchestration history violates the domain contract"
        ) from error


def _read_with_cursor(
    cursor: psycopg.Cursor, execution_id: PipelineExecutionId
) -> PipelineResult:
    cursor.execute(_PIPELINE_SELECT, (execution_id.value,))
    pipeline_row = cursor.fetchone()
    if pipeline_row is None:
        raise InvalidOrchestrationResultError(
            "Pipeline execution history was not found"
        )
    cursor.execute(_STAGES_SELECT, (execution_id.value,))
    return _reconstruct(pipeline_row, cursor.fetchall())


def _raise_pipeline_transition_error(
    cursor: psycopg.Cursor,
    execution_id: PipelineExecutionId,
    expected: str,
    target: str,
) -> None:
    cursor.execute(
        "SELECT state FROM pipeline_executions WHERE pipeline_execution_id = %s",
        (execution_id.value,),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidLifecycleTransitionError("Pipeline execution was not found")
    raise InvalidLifecycleTransitionError(
        f"Pipeline transition {row[0]} -> {target} is not governed; expected {expected}"
    )


def _raise_stage_transition_error(
    cursor: psycopg.Cursor,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    expected: str,
    target: str,
) -> None:
    cursor.execute(
        """
        SELECT state
        FROM pipeline_stage_executions
        WHERE pipeline_execution_id = %s AND stage = %s
        """,
        (execution_id.value, stage.name),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidLifecycleTransitionError("Pipeline stage execution was not found")
    raise InvalidLifecycleTransitionError(
        f"Stage transition {row[0]} -> {target} is not governed; expected {expected}"
    )


def create_pipeline_execution(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    created_at: datetime,
    predecessor_execution_id: PipelineExecutionId | None = None,
) -> PipelineResult:
    """Atomically create one pending pipeline and its three pending stages."""
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pipeline_executions (
                        pipeline_execution_id, predecessor_execution_id,
                        state, created_at
                    )
                    VALUES (%s, %s, 'PENDING', %s)
                    """,
                    (
                        execution_id.value,
                        predecessor_execution_id.value
                        if predecessor_execution_id is not None
                        else None,
                        created_at,
                    ),
                )
                cursor.executemany(
                    """
                    INSERT INTO pipeline_stage_executions (
                        pipeline_execution_id, stage, stage_sequence, state
                    )
                    VALUES (%s, %s, %s, 'PENDING')
                    """,
                    [
                        (execution_id.value, stage.name, stage.value)
                        for stage in StageIdentity
                    ],
                )
                return _read_with_cursor(cursor, execution_id)
    except psycopg.Error as error:
        raise OrchestrationPersistenceError(
            "Unable to create pipeline execution history"
        ) from error


def _transition_pipeline(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    expected: PipelineLifecycleState,
    target: PipelineLifecycleState,
    timestamp_column: str,
    timestamp: datetime,
    failure: FailureDetail | None = None,
) -> PipelineResult:
    sql = f"""
        UPDATE pipeline_executions
        SET state = %s, {timestamp_column} = %s,
            failure_category = %s, failure_code = %s
        WHERE pipeline_execution_id = %s AND state = %s
    """
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        target.value,
                        timestamp,
                        failure.category.value if failure is not None else None,
                        failure.code if failure is not None else None,
                        execution_id.value,
                        expected.value,
                    ),
                )
                if cursor.rowcount != 1:
                    _raise_pipeline_transition_error(
                        cursor, execution_id, expected.value, target.value
                    )
                return _read_with_cursor(cursor, execution_id)
    except psycopg.Error as error:
        raise OrchestrationPersistenceError(
            "Unable to update pipeline execution history"
        ) from error


def _transition_stage(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    expected: StageLifecycleState,
    target: StageLifecycleState,
    timestamp_column: str,
    timestamp: datetime,
    failure: FailureDetail | None = None,
) -> PipelineResult:
    sql = f"""
        UPDATE pipeline_stage_executions
        SET state = %s, {timestamp_column} = %s,
            failure_category = %s, failure_code = %s
        WHERE pipeline_execution_id = %s AND stage = %s AND state = %s
    """
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        target.value,
                        timestamp,
                        failure.category.value if failure is not None else None,
                        failure.code if failure is not None else None,
                        execution_id.value,
                        stage.name,
                        expected.value,
                    ),
                )
                if cursor.rowcount != 1:
                    _raise_stage_transition_error(
                        cursor, execution_id, stage, expected.value, target.value
                    )
                return _read_with_cursor(cursor, execution_id)
    except psycopg.Error as error:
        raise OrchestrationPersistenceError(
            "Unable to update pipeline stage execution history"
        ) from error


def mark_pipeline_running(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    started_at: datetime,
) -> PipelineResult:
    return _transition_pipeline(
        connection,
        execution_id,
        PipelineLifecycleState.PENDING,
        PipelineLifecycleState.RUNNING,
        "started_at",
        started_at,
    )


def mark_stage_running(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    started_at: datetime,
) -> PipelineResult:
    return _transition_stage(
        connection,
        execution_id,
        stage,
        StageLifecycleState.PENDING,
        StageLifecycleState.RUNNING,
        "started_at",
        started_at,
    )


def mark_stage_succeeded(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    completed_at: datetime,
) -> PipelineResult:
    return _transition_stage(
        connection,
        execution_id,
        stage,
        StageLifecycleState.RUNNING,
        StageLifecycleState.SUCCEEDED,
        "completed_at",
        completed_at,
    )


def mark_stage_failed(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    completed_at: datetime,
    failure: FailureDetail,
) -> PipelineResult:
    return _transition_stage(
        connection,
        execution_id,
        stage,
        StageLifecycleState.RUNNING,
        StageLifecycleState.FAILED,
        "completed_at",
        completed_at,
        failure,
    )


def mark_stage_skipped(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    stage: StageIdentity,
    completed_at: datetime,
) -> PipelineResult:
    return _transition_stage(
        connection,
        execution_id,
        stage,
        StageLifecycleState.PENDING,
        StageLifecycleState.SKIPPED,
        "completed_at",
        completed_at,
    )


def mark_pipeline_succeeded(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    completed_at: datetime,
) -> PipelineResult:
    return _transition_pipeline(
        connection,
        execution_id,
        PipelineLifecycleState.RUNNING,
        PipelineLifecycleState.SUCCEEDED,
        "completed_at",
        completed_at,
    )


def mark_pipeline_blocked(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    completed_at: datetime,
) -> PipelineResult:
    return _transition_pipeline(
        connection,
        execution_id,
        PipelineLifecycleState.RUNNING,
        PipelineLifecycleState.BLOCKED,
        "completed_at",
        completed_at,
    )


def mark_pipeline_failed(
    connection: psycopg.Connection,
    execution_id: PipelineExecutionId,
    completed_at: datetime,
    failure: FailureDetail,
) -> PipelineResult:
    return _transition_pipeline(
        connection,
        execution_id,
        PipelineLifecycleState.RUNNING,
        PipelineLifecycleState.FAILED,
        "completed_at",
        completed_at,
        failure,
    )


def read_execution(
    connection: psycopg.Connection, execution_id: PipelineExecutionId
) -> PipelineResult:
    """Read and reconstruct one complete immutable pipeline execution result."""
    try:
        with connection.cursor() as cursor:
            return _read_with_cursor(cursor, execution_id)
    except psycopg.Error as error:
        raise OrchestrationPersistenceError(
            "Unable to read pipeline execution history"
        ) from error
