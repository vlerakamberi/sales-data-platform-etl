"""Real-PostgreSQL physical-contract and drift validation tests."""

import psycopg
import pytest

from sales_data_platform.database.exceptions import DatabaseContractError
from sales_data_platform.database.migrations import (
    apply_migrations,
    discover_migrations,
    inspect_migration_history,
)
from sales_data_platform.database.seed import seed_sales_channels
from sales_data_platform.database.validation import (
    validate_database_contract,
    validate_sales_channel_reference_contract,
)

pytestmark = pytest.mark.postgresql


def test_current_database_provenance_schema_and_reference_state_validate(
    contract_connection: psycopg.Connection,
) -> None:
    assert apply_migrations(contract_connection) == ()
    assert [row.version for row in inspect_migration_history(contract_connection)] == [
        1,
        2,
        3,
        4,
    ]
    assert seed_sales_channels(contract_connection) == ("ECOMMERCE", "RETAIL")
    validate_database_contract(contract_connection)
    validate_sales_channel_reference_contract(contract_connection)
    assert seed_sales_channels(contract_connection) == ()


def test_older_valid_database_advances_then_validates(
    contract_connection: psycopg.Connection,
) -> None:
    with contract_connection.cursor() as cursor:
        cursor.execute("DROP TABLE pipeline_stage_executions")
        cursor.execute("DROP TABLE pipeline_executions")
        cursor.execute("DELETE FROM schema_migrations WHERE version = 4")
    migrations = discover_migrations()
    applied = apply_migrations(contract_connection, migrations)
    assert [migration.version for migration in applied] == [4]
    seed_sales_channels(contract_connection)
    validate_database_contract(contract_connection)
    assert [row.version for row in inspect_migration_history(contract_connection)] == [
        1,
        2,
        3,
        4,
    ]


@pytest.mark.parametrize(
    "drift_sql",
    [
        "ALTER TABLE products DROP CONSTRAINT ck_products_list_price_non_negative",
        "ALTER TABLE products ALTER COLUMN product_name DROP NOT NULL",
        "DROP INDEX ix_orders_order_timestamp",
        "ALTER TABLE products ALTER COLUMN list_price TYPE NUMERIC(12,2)",
        "ALTER TABLE stores DROP CONSTRAINT stores_store_code_key",
    ],
    ids=[
        "missing-check",
        "nullability",
        "missing-index",
        "numeric-domain",
        "uniqueness",
    ],
)
def test_representative_physical_drift_is_rejected(
    contract_connection: psycopg.Connection, drift_sql: str
) -> None:
    with contract_connection.cursor() as cursor:
        cursor.execute(drift_sql)
    with pytest.raises(DatabaseContractError, match="contract validation failed"):
        validate_database_contract(contract_connection)


def test_exact_sales_channel_reference_state_passes_without_mutation(
    contract_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(contract_connection)
    with contract_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        before = cursor.fetchall()

    validate_sales_channel_reference_contract(contract_connection)

    with contract_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        assert cursor.fetchall() == before


@pytest.mark.parametrize(
    "invalid_sql",
    [
        "DELETE FROM sales_channels WHERE sales_channel_code = 'ECOMMERCE'",
        "DELETE FROM sales_channels WHERE sales_channel_code = 'RETAIL'",
        "UPDATE sales_channels SET sales_channel_name = 'Wrong' "
        "WHERE sales_channel_code = 'ECOMMERCE'",
        "UPDATE sales_channels SET sales_channel_name = 'Wrong' "
        "WHERE sales_channel_code = 'RETAIL'",
        "INSERT INTO sales_channels (sales_channel_code, sales_channel_name) "
        "VALUES ('PARTNER', 'Partner')",
    ],
    ids=[
        "missing-ecommerce",
        "missing-retail",
        "conflicting-ecommerce",
        "conflicting-retail",
        "additional-partner",
    ],
)
def test_invalid_sales_channel_reference_state_is_rejected_without_mutation(
    contract_connection: psycopg.Connection, invalid_sql: str
) -> None:
    seed_sales_channels(contract_connection)
    with contract_connection.cursor() as cursor:
        cursor.execute(invalid_sql)
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        before = cursor.fetchall()

    with pytest.raises(DatabaseContractError, match="sales-channel-reference-data"):
        validate_sales_channel_reference_contract(contract_connection)

    with contract_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_id, sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        assert cursor.fetchall() == before


def test_extra_unapproved_table_is_rejected(
    contract_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(contract_connection)
    with contract_connection.cursor() as cursor:
        cursor.execute("CREATE TABLE commit5_unapproved_probe (probe_id INTEGER)")

    with pytest.raises(DatabaseContractError, match="tables"):
        validate_database_contract(contract_connection)


def test_extra_explicit_non_constraint_index_is_rejected(
    contract_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(contract_connection)
    with contract_connection.cursor() as cursor:
        cursor.execute("CREATE INDEX ix_products_name_extra ON products (product_name)")

    with pytest.raises(DatabaseContractError, match="indexes"):
        validate_database_contract(contract_connection)


def test_extra_expression_index_is_rejected(
    contract_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(contract_connection)
    with contract_connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE INDEX ix_products_lower_name_extra
            ON products ((lower(product_name)))
            """
        )

    with pytest.raises(DatabaseContractError, match="indexes"):
        validate_database_contract(contract_connection)
