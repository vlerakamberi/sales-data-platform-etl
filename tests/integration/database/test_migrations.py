"""Guarded real-PostgreSQL migration integration tests."""

from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from sales_data_platform.config.settings import Settings
from sales_data_platform.database.connection import connect_database
from sales_data_platform.database.exceptions import (
    MigrationExecutionError,
    MigrationStateError,
)
from sales_data_platform.database.migrations import (
    apply_migrations,
    discover_migrations,
    inspect_migration_history,
    parse_migration,
)

pytestmark = pytest.mark.postgresql

AUTHORIZED_TABLES_IN_DROP_ORDER = (
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
def migration_connection() -> psycopg.Connection:
    settings = Settings()
    if settings.database_name is None:
        pytest.skip("Dedicated PostgreSQL test database is not configured")
    if not settings.database_name.endswith("_test"):
        pytest.fail(
            "DATABASE_NAME must end with _test for migration integration tests",
            pytrace=False,
        )

    connection = connect_database(settings)
    _guard_test_database(connection, settings.database_name)
    _reset_repository_objects(connection)
    try:
        yield connection
    finally:
        _guard_test_database(connection, settings.database_name)
        _reset_repository_objects(connection)
        connection.close()


def test_clean_database_applies_v001_through_v003(
    migration_connection: psycopg.Connection,
) -> None:
    applied = apply_migrations(migration_connection)

    assert [migration.version for migration in applied] == [1, 2, 3]
    with migration_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name IN ('orders', 'order_items', 'schema_migrations')
            ORDER BY table_name
            """
        )
        assert [row[0] for row in cursor.fetchall()] == [
            "order_items",
            "orders",
            "schema_migrations",
        ]
        cursor.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = 'ix_orders_order_timestamp'
            """
        )
        assert cursor.fetchone() == ("ix_orders_order_timestamp",)


def test_current_database_does_not_reapply_migrations(
    migration_connection: psycopg.Connection,
) -> None:
    apply_migrations(migration_connection)

    assert apply_migrations(migration_connection) == ()


def test_older_valid_database_applies_only_missing_migration(
    migration_connection: psycopg.Connection,
) -> None:
    migrations = discover_migrations()
    apply_migrations(migration_connection, migrations[:2])

    applied = apply_migrations(migration_connection, migrations)

    assert [migration.version for migration in applied] == [3]


def test_changed_applied_checksum_is_rejected(
    migration_connection: psycopg.Connection,
) -> None:
    migrations = discover_migrations()
    apply_migrations(migration_connection, migrations)
    changed = (replace(migrations[0], checksum="0" * 64), *migrations[1:])

    with pytest.raises(MigrationStateError, match="checksum mismatch"):
        apply_migrations(migration_connection, changed)


def test_unknown_applied_migration_is_rejected(
    migration_connection: psycopg.Connection,
) -> None:
    apply_migrations(migration_connection)
    with migration_connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO schema_migrations (version, filename, checksum, applied_at)
            VALUES (999, 'V999__unknown.sql', %s, CURRENT_TIMESTAMP)
            """,
            ("0" * 64,),
        )

    with pytest.raises(MigrationStateError, match="Unknown applied migration"):
        apply_migrations(migration_connection)


def test_non_contiguous_history_is_rejected(
    migration_connection: psycopg.Connection,
) -> None:
    apply_migrations(migration_connection)
    with migration_connection.cursor() as cursor:
        cursor.execute("DELETE FROM schema_migrations WHERE version = 2")

    with pytest.raises(MigrationStateError, match="Non-contiguous"):
        apply_migrations(migration_connection)


def test_metadata_relation_missing_v001_checks_is_rejected(
    migration_connection: psycopg.Connection,
) -> None:
    with migration_connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                filename VARCHAR(255) NOT NULL UNIQUE,
                checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL
            )
            """
        )

    with pytest.raises(MigrationStateError, match="Incompatible"):
        apply_migrations(migration_connection)


def test_failed_migration_rolls_back_without_false_history(
    migration_connection: psycopg.Connection, tmp_path: Path
) -> None:
    migrations = discover_migrations()
    apply_migrations(migration_connection, migrations)
    failed_path = tmp_path / "V004__fail_transaction.sql"
    failed_path.write_text(
        "CREATE TABLE commit3_failure_probe (probe_id INTEGER);\nINVALID SQL;\n",
        encoding="utf-8",
    )
    failed = parse_migration(failed_path)

    with pytest.raises(MigrationExecutionError, match=failed.filename):
        apply_migrations(migration_connection, (*migrations, failed))

    with migration_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 4")
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT to_regclass('commit3_failure_probe')")
        assert cursor.fetchone() == (None,)


def test_migration_history_records_authoritative_identity(
    migration_connection: psycopg.Connection,
) -> None:
    migrations = discover_migrations()
    apply_migrations(migration_connection, migrations)

    history = inspect_migration_history(migration_connection)

    assert [(row.version, row.filename, row.checksum) for row in history] == [
        (migration.version, migration.filename, migration.checksum)
        for migration in migrations
    ]
