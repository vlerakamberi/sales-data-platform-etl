"""Unit tests for narrow orchestration-history persistence behavior."""

from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import psycopg
import pytest

from sales_data_platform.orchestration import history
from sales_data_platform.orchestration.errors import (
    InvalidLifecycleTransitionError,
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
)

NOW = datetime(2026, 8, 12, 10, tzinfo=UTC)


def _connection(cursor: MagicMock) -> MagicMock:
    connection = MagicMock(spec=psycopg.Connection)
    connection.transaction.return_value = nullcontext()
    connection.cursor.return_value = nullcontext(cursor)
    return connection


def _result() -> MagicMock:
    return MagicMock(spec=PipelineResult)


def test_creation_uses_one_transaction_parameterized_sql_and_three_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    connection = _connection(cursor)
    execution_id = PipelineExecutionId(uuid4())
    predecessor = PipelineExecutionId(uuid4())
    expected = _result()
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: expected)

    result = history.create_pipeline_execution(
        connection, execution_id, NOW, predecessor
    )

    assert result is expected
    connection.transaction.assert_called_once_with()
    insert_sql, insert_params = cursor.execute.call_args.args
    assert "%s" in insert_sql
    assert insert_params == (execution_id.value, predecessor.value, NOW)
    stage_sql, stage_params = cursor.executemany.call_args.args
    assert "%s" in stage_sql
    assert stage_params == [
        (execution_id.value, "INGESTION", 1),
        (execution_id.value, "TRANSFORMATION", 2),
        (execution_id.value, "DATA_QUALITY", 3),
    ]


def test_creation_accepts_no_predecessor(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    connection = _connection(cursor)
    execution_id = PipelineExecutionId(uuid4())
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: _result())

    history.create_pipeline_execution(connection, execution_id, NOW)

    assert cursor.execute.call_args.args[1][1] is None


@pytest.mark.parametrize(
    ("operation", "expected", "target"),
    [
        (history.mark_pipeline_running, "PENDING", "RUNNING"),
        (history.mark_pipeline_succeeded, "RUNNING", "SUCCEEDED"),
        (history.mark_pipeline_blocked, "RUNNING", "BLOCKED"),
    ],
)
def test_pipeline_mutations_use_expected_prior_state_and_one_transaction(
    monkeypatch: pytest.MonkeyPatch, operation, expected: str, target: str
) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.rowcount = 1
    connection = _connection(cursor)
    execution_id = PipelineExecutionId(uuid4())
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: _result())

    operation(connection, execution_id, NOW)

    connection.transaction.assert_called_once_with()
    sql, params = cursor.execute.call_args_list[0].args
    assert "pipeline_execution_id = %s AND state = %s" in sql
    assert params[0] == target
    assert params[-1] == expected


@pytest.mark.parametrize(
    ("operation", "expected", "target"),
    [
        (history.mark_stage_running, "PENDING", "RUNNING"),
        (history.mark_stage_skipped, "PENDING", "SKIPPED"),
        (history.mark_stage_succeeded, "RUNNING", "SUCCEEDED"),
    ],
)
def test_stage_mutations_use_expected_prior_state_and_one_transaction(
    monkeypatch: pytest.MonkeyPatch, operation, expected: str, target: str
) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.rowcount = 1
    connection = _connection(cursor)
    execution_id = PipelineExecutionId(uuid4())
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: _result())

    operation(connection, execution_id, StageIdentity.INGESTION, NOW)

    connection.transaction.assert_called_once_with()
    sql, params = cursor.execute.call_args_list[0].args
    assert "stage = %s AND state = %s" in sql
    assert params[0] == target
    assert params[-1] == expected


@pytest.mark.parametrize(
    "operation",
    [history.mark_pipeline_failed, history.mark_stage_failed],
)
def test_failed_transitions_persist_controlled_failure(operation, monkeypatch) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.rowcount = 1
    connection = _connection(cursor)
    execution_id = PipelineExecutionId(uuid4())
    failure = FailureDetail(FailureClassification.PERSISTENCE_FAILURE, "WRITE.FAIL")
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: _result())

    if operation is history.mark_pipeline_failed:
        operation(connection, execution_id, NOW, failure)
    else:
        operation(connection, execution_id, StageIdentity.INGESTION, NOW, failure)

    params = cursor.execute.call_args_list[0].args[1]
    assert "PERSISTENCE_FAILURE" in params
    assert "WRITE.FAIL" in params


def test_zero_updated_rows_rejects_illegal_and_terminal_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.rowcount = 0
    cursor.fetchone.return_value = ("SUCCEEDED",)
    connection = _connection(cursor)
    monkeypatch.setattr(history, "_read_with_cursor", lambda *_: _result())

    with pytest.raises(InvalidLifecycleTransitionError, match="SUCCEEDED"):
        history.mark_pipeline_succeeded(connection, PipelineExecutionId(uuid4()), NOW)

    assert cursor.execute.call_count == 2


def test_database_error_is_translated_once_without_retry() -> None:
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.execute.side_effect = psycopg.OperationalError("private database detail")
    connection = _connection(cursor)

    with pytest.raises(
        OrchestrationPersistenceError,
        match="Unable to update pipeline execution history",
    ) as raised:
        history.mark_pipeline_running(connection, PipelineExecutionId(uuid4()), NOW)

    assert "private database detail" not in str(raised.value)
    assert cursor.execute.call_count == 1
    connection.transaction.assert_called_once_with()


def test_read_reconstructs_uuid_predecessor_failures_and_ordered_stages() -> None:
    execution_uuid = uuid4()
    predecessor_uuid = uuid4()
    cursor = MagicMock(spec=psycopg.Cursor)
    cursor.fetchone.return_value = (
        execution_uuid,
        predecessor_uuid,
        "FAILED",
        NOW,
        NOW,
        NOW,
        "UNEXPECTED_EXECUTION_FAILURE",
        "PIPELINE.FAIL",
    )
    cursor.fetchall.return_value = [
        ("INGESTION", "SUCCEEDED", NOW, NOW, None, None),
        ("TRANSFORMATION", "FAILED", NOW, NOW, "TRANSFORMATION_FAILURE", "XFORM.FAIL"),
        ("DATA_QUALITY", "SKIPPED", None, NOW, None, None),
    ]
    result = history.read_execution(
        _connection(cursor), PipelineExecutionId(execution_uuid)
    )

    assert isinstance(result.execution_id.value, UUID)
    assert result.predecessor_execution_id == PipelineExecutionId(predecessor_uuid)
    assert result.state is PipelineLifecycleState.FAILED
    assert [stage.stage for stage in result.stages] == list(StageIdentity)
    assert result.stages[1].state is StageLifecycleState.FAILED
    assert result.stages[1].failure.code == "XFORM.FAIL"
