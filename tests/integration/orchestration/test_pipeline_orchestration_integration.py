"""Real-PostgreSQL integration test for deterministic pipeline orchestration."""

from pathlib import Path

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.migrations import apply_migrations
from sales_data_platform.ingestion.contracts import SourceContractKey
from sales_data_platform.orchestration.history import read_execution
from sales_data_platform.orchestration.models import (
    PipelineLifecycleState,
    StageIdentity,
    StageLifecycleState,
)
from sales_data_platform.orchestration.service import run_pipeline

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
