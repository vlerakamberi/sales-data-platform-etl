"""Real-PostgreSQL integration test for deterministic pipeline orchestration."""

from pathlib import Path

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.migrations import apply_migrations
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.orchestration import service as orchestration_service
from sales_data_platform.orchestration.history import read_execution
from sales_data_platform.orchestration.models import (
    FailureClassification,
    PipelineLifecycleState,
    StageIdentity,
    StageLifecycleState,
)
from sales_data_platform.orchestration.service import run_pipeline
from sales_data_platform.quality.expectations import (
    PRODUCT_SKU_UNIQUENESS_DEFINITION,
)
from sales_data_platform.quality.models import QualityDisposition

pytestmark = pytest.mark.postgresql

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "ingestion" / "data" / "raw"
)
PRODUCT_KEY = SourceContractKey("northstar.product_catalog", 1)
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
def pipeline_connection() -> psycopg.Connection:
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


def test_product_pipeline_executes_all_layers_and_returns_durable_result(
    pipeline_connection: psycopg.Connection,
) -> None:
    settings = Settings(_env_file=None, INGESTION_SOURCE_ROOT=FIXTURE_ROOT)
    result = run_pipeline(
        pipeline_connection,
        contract_key=PRODUCT_KEY,
        source_path=FIXTURE_ROOT / "product_catalog" / "v1" / "products.csv",
        settings=settings,
    )

    assert result.state is PipelineLifecycleState.SUCCEEDED
    assert result.predecessor_execution_id is None
    assert [stage.stage for stage in result.stages] == list(StageIdentity)
    assert all(stage.state is StageLifecycleState.SUCCEEDED for stage in result.stages)
    assert result == read_execution(pipeline_connection, result.execution_id)

    with pipeline_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT stage, stage_sequence, state
            FROM pipeline_stage_executions
            WHERE pipeline_execution_id = %s
            ORDER BY stage_sequence
            """,
            (result.execution_id.value,),
        )
        assert cursor.fetchall() == [
            ("INGESTION", 1, "SUCCEEDED"),
            ("TRANSFORMATION", 2, "SUCCEEDED"),
            ("DATA_QUALITY", 3, "SUCCEEDED"),
        ]
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name IN (
                  'pipeline_executions', 'pipeline_stage_executions'
              )
              AND column_name = 'run_id'
            """
        )
        assert cursor.fetchall() == []


def test_duplicate_product_sku_naturally_blocks_durable_pipeline(
    pipeline_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "product_catalog" / "v1" / "products.csv"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "sku,product_name,category_code,list_price,unit_cost,currency_code\n"
        "SKU-DUPLICATE,Trail Bottle,OUTDOOR,24.99,10.50,EUR\n"
        "SKU-DUPLICATE,Travel Mug,HOME,19.99,8.00,EUR\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=None, INGESTION_SOURCE_ROOT=tmp_path)

    result = run_pipeline(
        pipeline_connection,
        contract_key=PRODUCT_KEY,
        source_path=source_path,
        settings=settings,
    )

    assert PRODUCT_SKU_UNIQUENESS_DEFINITION.key.expectation_id == "DQ-PRODUCT-001"
    assert (
        PRODUCT_SKU_UNIQUENESS_DEFINITION.violation_disposition
        is QualityDisposition.BLOCKING
    )
    assert result.state is PipelineLifecycleState.BLOCKED
    assert result.failure is None
    assert [stage.state for stage in result.stages] == [
        StageLifecycleState.SUCCEEDED,
        StageLifecycleState.SUCCEEDED,
        StageLifecycleState.SUCCEEDED,
    ]
    assert all(stage.failure is None for stage in result.stages)
    assert result == read_execution(pipeline_connection, result.execution_id)


def test_transformation_failure_preserves_durable_partial_progress(
    pipeline_connection: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_transformation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("deterministic integrated test failure")

    monkeypatch.setattr(
        orchestration_service,
        "transform_batch",
        fail_transformation,
    )
    settings = Settings(_env_file=None, INGESTION_SOURCE_ROOT=FIXTURE_ROOT)

    result = run_pipeline(
        pipeline_connection,
        contract_key=PRODUCT_KEY,
        source_path=FIXTURE_ROOT / "product_catalog" / "v1" / "products.csv",
        settings=settings,
    )

    assert result.state is PipelineLifecycleState.FAILED
    assert result.state is not PipelineLifecycleState.BLOCKED
    assert result.failure is not None
    assert result.failure.category is FailureClassification.UNEXPECTED_EXECUTION_FAILURE
    assert result.failure.code == "UNEXPECTED_EXECUTION_ERROR"
    assert [stage.state for stage in result.stages] == [
        StageLifecycleState.SUCCEEDED,
        StageLifecycleState.FAILED,
        StageLifecycleState.SKIPPED,
    ]
    assert result.stages[0].failure is None
    assert result.stages[1].failure == result.failure
    assert result.stages[2].failure is None
    assert result == read_execution(pipeline_connection, result.execution_id)


def test_deterministic_replay_creates_separate_durable_execution_histories(
    pipeline_connection: psycopg.Connection,
) -> None:
    settings = Settings(_env_file=None, INGESTION_SOURCE_ROOT=FIXTURE_ROOT)
    source_path = FIXTURE_ROOT / "product_catalog" / "v1" / "products.csv"

    first = run_pipeline(
        pipeline_connection,
        contract_key=PRODUCT_KEY,
        source_path=source_path,
        settings=settings,
    )
    second = run_pipeline(
        pipeline_connection,
        contract_key=PRODUCT_KEY,
        source_path=source_path,
        settings=settings,
    )

    assert first.execution_id != second.execution_id
    assert first.predecessor_execution_id is None
    assert second.predecessor_execution_id is None
    assert first.state is second.state is PipelineLifecycleState.SUCCEEDED
    assert (
        [stage.state for stage in first.stages]
        == [stage.state for stage in second.stages]
        == [
            StageLifecycleState.SUCCEEDED,
            StageLifecycleState.SUCCEEDED,
            StageLifecycleState.SUCCEEDED,
        ]
    )
    assert first == read_execution(pipeline_connection, first.execution_id)
    assert second == read_execution(pipeline_connection, second.execution_id)

    with pipeline_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT pipeline_execution_id, state
            FROM pipeline_executions
            WHERE pipeline_execution_id IN (%s, %s)
            ORDER BY pipeline_execution_id
            """,
            (first.execution_id.value, second.execution_id.value),
        )
        assert set(cursor.fetchall()) == {
            (first.execution_id.value, "SUCCEEDED"),
            (second.execution_id.value, "SUCCEEDED"),
        }
        cursor.execute(
            """
            SELECT pipeline_execution_id, stage, state
            FROM pipeline_stage_executions
            WHERE pipeline_execution_id IN (%s, %s)
            ORDER BY pipeline_execution_id, stage_sequence
            """,
            (first.execution_id.value, second.execution_id.value),
        )
        histories = cursor.fetchall()
        assert len(histories) == 6
        for execution_id in (first.execution_id.value, second.execution_id.value):
            assert [row[1:] for row in histories if row[0] == execution_id] == [
                ("INGESTION", "SUCCEEDED"),
                ("TRANSFORMATION", "SUCCEEDED"),
                ("DATA_QUALITY", "SUCCEEDED"),
            ]
