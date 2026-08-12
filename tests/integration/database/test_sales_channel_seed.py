"""Guarded real-PostgreSQL sales-channel reference-data tests."""

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.exceptions import ReferenceDataConflictError
from sales_data_platform.database.migrations import apply_migrations
from sales_data_platform.database.seed import seed_sales_channels

pytestmark = pytest.mark.postgresql

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
EXPECTED_ROWS = [
    ("ECOMMERCE", "E-Commerce"),
    ("RETAIL", "Retail"),
]


def _guard_test_database(connection: psycopg.Connection, configured_name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    actual_name = row[0] if row else None
    if actual_name != configured_name or not configured_name.endswith("_test"):
        pytest.fail(
            "PostgreSQL test safety guard rejected the connected database",
            pytrace=False,
        )


def _reset_repository_objects(connection: psycopg.Connection) -> None:
    for table in AUTHORIZED_TABLES_IN_DROP_ORDER:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


@pytest.fixture
def seed_connection() -> psycopg.Connection:
    settings = Settings()
    if settings.database_name is None:
        pytest.skip("Dedicated PostgreSQL test database is not configured")
    if not settings.database_name.endswith("_test"):
        pytest.fail(
            "DATABASE_NAME must end with _test for reference-data integration tests",
            pytrace=False,
        )

    connection = connect_database(settings)
    _guard_test_database(connection, settings.database_name)
    _reset_repository_objects(connection)
    apply_migrations(connection)
    try:
        yield connection
    finally:
        _guard_test_database(connection, settings.database_name)
        _reset_repository_objects(connection)
        connection.close()


def _rows(connection: psycopg.Connection) -> list[tuple[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        return cursor.fetchall()


def test_empty_reference_state_inserts_exact_approved_rows(
    seed_connection: psycopg.Connection,
) -> None:
    assert seed_sales_channels(seed_connection) == ("ECOMMERCE", "RETAIL")
    assert _rows(seed_connection) == EXPECTED_ROWS


def test_correct_state_replay_is_idempotent(
    seed_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(seed_connection)
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        before = cursor.fetchall()

    assert seed_sales_channels(seed_connection) == ()

    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        assert cursor.fetchall() == before


def test_one_existing_row_is_preserved_and_only_missing_row_is_inserted(
    seed_connection: psycopg.Connection,
) -> None:
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
            VALUES ('ECOMMERCE', 'E-Commerce')
            RETURNING sales_channel_id
            """
        )
        existing_id = cursor.fetchone()[0]

    assert seed_sales_channels(seed_connection) == ("RETAIL",)

    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id
            FROM sales_channels
            WHERE sales_channel_code = 'ECOMMERCE'
            """
        )
        assert cursor.fetchone() == (existing_id,)
    assert _rows(seed_connection) == EXPECTED_ROWS


def test_ecommerce_name_conflict_fails_without_overwrite(
    seed_connection: psycopg.Connection,
) -> None:
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
            VALUES ('ECOMMERCE', 'Conflicting Name')
            """
        )

    with pytest.raises(ReferenceDataConflictError, match="ECOMMERCE"):
        seed_sales_channels(seed_connection)

    assert _rows(seed_connection) == [("ECOMMERCE", "Conflicting Name")]


def test_retail_name_conflict_fails_without_overwrite(
    seed_connection: psycopg.Connection,
) -> None:
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
            VALUES ('RETAIL', 'Conflicting Name')
            """
        )

    with pytest.raises(ReferenceDataConflictError, match="RETAIL"):
        seed_sales_channels(seed_connection)

    assert _rows(seed_connection) == [("RETAIL", "Conflicting Name")]


def test_conflict_prevents_partial_reference_data_convergence(
    seed_connection: psycopg.Connection,
) -> None:
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
            VALUES ('ECOMMERCE', 'Conflicting Name')
            """
        )

    with pytest.raises(ReferenceDataConflictError):
        seed_sales_channels(seed_connection)

    assert _rows(seed_connection) == [("ECOMMERCE", "Conflicting Name")]


def test_unexpected_unrelated_row_is_preserved(
    seed_connection: psycopg.Connection,
) -> None:
    with seed_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sales_channels (sales_channel_code, sales_channel_name)
            VALUES ('PARTNER', 'Partner')
            """
        )

    seed_sales_channels(seed_connection)

    assert _rows(seed_connection) == [
        ("ECOMMERCE", "E-Commerce"),
        ("PARTNER", "Partner"),
        ("RETAIL", "Retail"),
    ]


def test_dedicated_database_safety_guard_rejects_mismatched_target(
    seed_connection: psycopg.Connection,
) -> None:
    with pytest.raises(pytest.fail.Exception, match="safety guard rejected"):
        _guard_test_database(seed_connection, "sales_data_platform")
