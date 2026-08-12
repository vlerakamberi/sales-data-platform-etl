"""Guarded real-PostgreSQL tests for durable pipeline execution history."""

# ruff: noqa: E501

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.migrations import (
    apply_migrations,
    inspect_migration_history,
)
from sales_data_platform.database.seed import seed_sales_channels
from sales_data_platform.database.validation import validate_database_contract
from sales_data_platform.orchestration.errors import InvalidLifecycleTransitionError
from sales_data_platform.orchestration.history import (
    create_pipeline_execution,
    mark_pipeline_blocked,
    mark_pipeline_failed,
    mark_pipeline_running,
    mark_pipeline_succeeded,
    mark_stage_failed,
    mark_stage_running,
    mark_stage_skipped,
    mark_stage_succeeded,
    read_execution,
)
from sales_data_platform.orchestration.models import (
    FailureClassification,
    FailureDetail,
    PipelineExecutionId,
    PipelineLifecycleState,
    StageIdentity,
    StageLifecycleState,
)

pytestmark = pytest.mark.postgresql

NOW = datetime(2026, 8, 12, 10, tzinfo=UTC)
AUTHORIZED_TABLES_IN_DROP_ORDER = (
    "pipeline_stage_executions",
    "pipeline_executions",
    "returns",
    "payments",
    "order_items",
    "orders",
    "products",
    "product_categories",
    "customers",
    "stores",
    "sales_channels",
    "schema_migrations",
)


def _guard(connection: psycopg.Connection, configured_name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    if not row or row[0] != configured_name or not configured_name.endswith("_test"):
        pytest.fail(
            "PostgreSQL test safety guard rejected the connected database",
            pytrace=False,
        )


def _reset(connection: psycopg.Connection) -> None:
    for table in AUTHORIZED_TABLES_IN_DROP_ORDER:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


@pytest.fixture
def history_connection() -> psycopg.Connection:
    settings = Settings()
    if settings.database_name is None:
        pytest.skip("Dedicated PostgreSQL test database is not configured")
    if not settings.database_name.endswith("_test"):
        pytest.fail("DATABASE_NAME must end with _test", pytrace=False)
    connection = connect_database(settings)
    _guard(connection, settings.database_name)
    _reset(connection)
    apply_migrations(connection)
    try:
        yield connection
    finally:
        _guard(connection, settings.database_name)
        _reset(connection)
        connection.close()


def _new_execution(connection: psycopg.Connection) -> PipelineExecutionId:
    execution_id = PipelineExecutionId(uuid4())
    create_pipeline_execution(connection, execution_id, NOW)
    return execution_id


def test_v004_applies_and_exact_physical_contract_validates(
    history_connection: psycopg.Connection,
) -> None:
    assert [row.version for row in inspect_migration_history(history_connection)] == [
        1,
        2,
        3,
        4,
    ]
    seed_sales_channels(history_connection)
    validate_database_contract(history_connection)
    with history_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name LIKE 'pipeline%executions'
            ORDER BY table_name
            """
        )
        assert cursor.fetchall() == [
            ("pipeline_executions",),
            ("pipeline_stage_executions",),
        ]
        cursor.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname LIKE 'ix_pipeline%'
            ORDER BY indexname
            """
        )
        assert cursor.fetchall() == [
            ("ix_pipeline_executions_predecessor",),
            ("ix_pipeline_executions_state",),
            ("ix_pipeline_stage_executions_pipeline",),
        ]


def test_creation_persists_exact_ordered_pending_shape_and_predecessor(
    history_connection: psycopg.Connection,
) -> None:
    predecessor = _new_execution(history_connection)
    execution_id = PipelineExecutionId(uuid4())
    result = create_pipeline_execution(
        history_connection, execution_id, NOW, predecessor
    )

    assert result.execution_id == execution_id
    assert result.predecessor_execution_id == predecessor
    assert result.state is PipelineLifecycleState.PENDING
    assert [stage.stage for stage in result.stages] == list(StageIdentity)
    assert all(stage.state is StageLifecycleState.PENDING for stage in result.stages)
    with history_connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pipeline_stage_executions WHERE pipeline_execution_id=%s",
            (execution_id.value,),
        )
        assert cursor.fetchone() == (3,)


def test_legal_stage_and_pipeline_transitions_round_trip_failures_and_skips(
    history_connection: psycopg.Connection,
) -> None:
    execution_id = _new_execution(history_connection)
    mark_pipeline_running(history_connection, execution_id, NOW + timedelta(minutes=1))
    mark_stage_running(
        history_connection,
        execution_id,
        StageIdentity.INGESTION,
        NOW + timedelta(minutes=2),
    )
    mark_stage_succeeded(
        history_connection,
        execution_id,
        StageIdentity.INGESTION,
        NOW + timedelta(minutes=3),
    )
    mark_stage_running(
        history_connection,
        execution_id,
        StageIdentity.TRANSFORMATION,
        NOW + timedelta(minutes=4),
    )
    failure = FailureDetail(FailureClassification.TRANSFORMATION_FAILURE, "XFORM.FAIL")
    mark_stage_failed(
        history_connection,
        execution_id,
        StageIdentity.TRANSFORMATION,
        NOW + timedelta(minutes=5),
        failure,
    )
    mark_stage_skipped(
        history_connection,
        execution_id,
        StageIdentity.DATA_QUALITY,
        NOW + timedelta(minutes=6),
    )
    pipeline_failure = FailureDetail(
        FailureClassification.UNEXPECTED_EXECUTION_FAILURE, "PIPELINE.FAIL"
    )
    result = mark_pipeline_failed(
        history_connection, execution_id, NOW + timedelta(minutes=7), pipeline_failure
    )

    assert result.state is PipelineLifecycleState.FAILED
    assert result.failure == pipeline_failure
    assert result.stages[1].failure == failure
    assert result.stages[2].state is StageLifecycleState.SKIPPED


@pytest.mark.parametrize(
    ("terminal", "expected_state"),
    [
        (mark_pipeline_succeeded, PipelineLifecycleState.SUCCEEDED),
        (mark_pipeline_blocked, PipelineLifecycleState.BLOCKED),
    ],
)
def test_success_and_blocked_are_terminal_without_failure(
    history_connection: psycopg.Connection, terminal, expected_state
) -> None:
    execution_id = _new_execution(history_connection)
    mark_pipeline_running(history_connection, execution_id, NOW + timedelta(minutes=1))
    result = terminal(history_connection, execution_id, NOW + timedelta(minutes=2))
    assert result.state is expected_state
    assert result.failure is None
    with pytest.raises(InvalidLifecycleTransitionError):
        terminal(history_connection, execution_id, NOW + timedelta(minutes=3))
    assert read_execution(history_connection, execution_id).state is expected_state


def test_illegal_stage_transition_is_rejected_without_mutation(
    history_connection: psycopg.Connection,
) -> None:
    execution_id = _new_execution(history_connection)
    with pytest.raises(InvalidLifecycleTransitionError):
        mark_stage_succeeded(
            history_connection, execution_id, StageIdentity.INGESTION, NOW
        )
    assert (
        read_execution(history_connection, execution_id).stages[0].state
        is StageLifecycleState.PENDING
    )


def test_committed_progress_is_visible_after_reconnect_and_survives_later_failure(
    history_connection: psycopg.Connection,
) -> None:
    execution_id = _new_execution(history_connection)
    mark_pipeline_running(history_connection, execution_id, NOW + timedelta(minutes=1))
    mark_stage_running(
        history_connection,
        execution_id,
        StageIdentity.INGESTION,
        NOW + timedelta(minutes=2),
    )

    settings = Settings()
    second = connect_database(settings)
    try:
        _guard(second, settings.database_name)
        result = read_execution(second, execution_id)
        assert result.state is PipelineLifecycleState.RUNNING
        assert result.stages[0].state is StageLifecycleState.RUNNING
        with pytest.raises(InvalidLifecycleTransitionError):
            mark_stage_skipped(
                second,
                execution_id,
                StageIdentity.INGESTION,
                NOW + timedelta(minutes=3),
            )
    finally:
        second.close()

    result = read_execution(history_connection, execution_id)
    assert result.state is PipelineLifecycleState.RUNNING
    assert result.stages[0].state is StageLifecycleState.RUNNING


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO pipeline_executions(pipeline_execution_id,state,created_at) VALUES(gen_random_uuid(),'INVALID',CURRENT_TIMESTAMP)",
        "INSERT INTO pipeline_executions(pipeline_execution_id,predecessor_execution_id,state,created_at) SELECT pipeline_execution_id,pipeline_execution_id,'PENDING',created_at FROM pipeline_executions LIMIT 1",
        "INSERT INTO pipeline_stage_executions(pipeline_execution_id,stage,stage_sequence,state) SELECT pipeline_execution_id,'INGESTION',2,'PENDING' FROM pipeline_executions LIMIT 1",
        "INSERT INTO pipeline_stage_executions(pipeline_execution_id,stage,stage_sequence,state) SELECT pipeline_execution_id,'INGESTION',1,'INVALID' FROM pipeline_executions LIMIT 1",
    ],
)
def test_governed_checks_reject_invalid_physical_rows(
    history_connection: psycopg.Connection, sql: str
) -> None:
    _new_execution(history_connection)
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        history_connection.cursor() as cursor,
    ):
        cursor.execute(sql)


def test_foreign_keys_uniqueness_timestamps_and_failure_consistency(
    history_connection: psycopg.Connection,
) -> None:
    execution_id = _new_execution(history_connection)
    statements = [
        (
            psycopg.errors.ForeignKeyViolation,
            "INSERT INTO pipeline_stage_executions(pipeline_execution_id,stage,stage_sequence,state) VALUES(%s,'INGESTION',1,'PENDING')",
            (uuid4(),),
        ),
        (
            psycopg.errors.UniqueViolation,
            "INSERT INTO pipeline_stage_executions(pipeline_execution_id,stage,stage_sequence,state) VALUES(%s,'INGESTION',1,'PENDING')",
            (execution_id.value,),
        ),
        (
            psycopg.errors.CheckViolation,
            "UPDATE pipeline_executions SET started_at=created_at-interval '1 second' WHERE pipeline_execution_id=%s",
            (execution_id.value,),
        ),
        (
            psycopg.errors.CheckViolation,
            "UPDATE pipeline_executions SET state='FAILED',completed_at=created_at WHERE pipeline_execution_id=%s",
            (execution_id.value,),
        ),
    ]
    for error, sql, params in statements:
        with pytest.raises(error), history_connection.cursor() as cursor:
            cursor.execute(sql, params)
