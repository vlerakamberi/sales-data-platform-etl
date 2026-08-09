"""Shared guarded PostgreSQL fixtures for database-contract tests."""

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.migrations import apply_migrations

AUTHORIZED_TABLES_IN_DROP_ORDER = (
    "commit5_unapproved_probe",
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


def guard_test_database(connection: psycopg.Connection, configured_name: str) -> None:
    """Reject any connection outside the configured dedicated test database."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    if not row or row[0] != configured_name or not configured_name.endswith("_test"):
        pytest.fail(
            "PostgreSQL test safety guard rejected the connected database",
            pytrace=False,
        )


def reset_repository_objects(connection: psycopg.Connection) -> None:
    """Drop only allowlisted Repository 1 relations."""
    for table in AUTHORIZED_TABLES_IN_DROP_ORDER:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS "{table}"')


@pytest.fixture
def contract_connection() -> psycopg.Connection:
    """Provide a current migrated database protected by the test-target guard."""
    settings = Settings()
    if settings.database_name is None:
        pytest.skip("Dedicated PostgreSQL test database is not configured")
    if not settings.database_name.endswith("_test"):
        pytest.fail("DATABASE_NAME must end with _test", pytrace=False)
    connection = connect_database(settings)
    guard_test_database(connection, settings.database_name)
    reset_repository_objects(connection)
    apply_migrations(connection)
    try:
        yield connection
    finally:
        guard_test_database(connection, settings.database_name)
        reset_repository_objects(connection)
        connection.close()
