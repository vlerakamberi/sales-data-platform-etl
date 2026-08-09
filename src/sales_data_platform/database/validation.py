"""Explicit validation of the Repository 1 Milestone 2 PostgreSQL contract."""

# ruff: noqa: E501

import re

import psycopg

from sales_data_platform.database.exceptions import DatabaseContractError

IDENTITY = ("bigint", "NO", None, 64, 0, "YES", "BY DEFAULT", True)
EXPECTED_TABLES = {
    "schema_migrations",
    "sales_channels",
    "stores",
    "customers",
    "product_categories",
    "products",
    "orders",
    "order_items",
    "payments",
    "returns",
}
EXPECTED_SALES_CHANNELS = (
    ("ECOMMERCE", "E-Commerce"),
    ("RETAIL", "Retail"),
)
EXPECTED_COLUMNS = {
    "sales_channels": (
        ("sales_channel_id", *IDENTITY),
        (
            "sales_channel_code",
            "character varying",
            "NO",
            32,
            None,
            None,
            "NO",
            None,
            True,
        ),
        (
            "sales_channel_name",
            "character varying",
            "NO",
            100,
            None,
            None,
            "NO",
            None,
            True,
        ),
    ),
    "stores": (
        ("store_id", *IDENTITY),
        ("store_code", "character varying", "NO", 50, None, None, "NO", None, True),
        ("store_name", "character varying", "NO", 200, None, None, "NO", None, True),
        ("country_code", "character", "NO", 2, None, None, "NO", None, True),
    ),
    "customers": (("customer_id", *IDENTITY),),
    "product_categories": (
        ("product_category_id", *IDENTITY),
        ("category_code", "character varying", "NO", 50, None, None, "NO", None, True),
        ("category_name", "character varying", "NO", 200, None, None, "NO", None, True),
    ),
    "products": (
        ("product_id", *IDENTITY),
        ("sku", "character varying", "NO", 100, None, None, "NO", None, True),
        ("product_name", "character varying", "NO", 255, None, None, "NO", None, True),
        ("product_category_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        ("list_price", "numeric", "YES", None, 18, 2, "NO", None, True),
        ("unit_cost", "numeric", "YES", None, 18, 2, "NO", None, True),
        ("currency_code", "character", "YES", 3, None, None, "NO", None, True),
    ),
    "orders": (
        ("order_id", *IDENTITY),
        ("sales_channel_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        ("store_id", "bigint", "YES", None, 64, 0, "NO", None, True),
        ("customer_id", "bigint", "YES", None, 64, 0, "NO", None, True),
        (
            "order_timestamp",
            "timestamp with time zone",
            "NO",
            None,
            None,
            None,
            "NO",
            None,
            True,
        ),
        ("currency_code", "character", "NO", 3, None, None, "NO", None, True),
        ("order_amount", "numeric", "YES", None, 18, 2, "NO", None, True),
    ),
    "order_items": (
        ("order_item_id", *IDENTITY),
        ("order_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        ("line_number", "integer", "NO", None, 32, 0, "NO", None, True),
        ("product_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        ("quantity", "integer", "NO", None, 32, 0, "NO", None, True),
        ("unit_price", "numeric", "NO", None, 18, 2, "NO", None, True),
        ("discount_amount", "numeric", "YES", None, 18, 2, "NO", None, True),
        ("line_amount", "numeric", "NO", None, 18, 2, "NO", None, True),
    ),
    "payments": (
        ("payment_id", *IDENTITY),
        ("order_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        (
            "payment_timestamp",
            "timestamp with time zone",
            "NO",
            None,
            None,
            None,
            "NO",
            None,
            True,
        ),
        ("payment_status", "character varying", "NO", 50, None, None, "NO", None, True),
        ("payment_amount", "numeric", "NO", None, 18, 2, "NO", None, True),
    ),
    "returns": (
        ("return_id", *IDENTITY),
        ("order_item_id", "bigint", "NO", None, 64, 0, "NO", None, True),
        (
            "return_timestamp",
            "timestamp with time zone",
            "NO",
            None,
            None,
            None,
            "NO",
            None,
            True,
        ),
        ("return_quantity", "integer", "NO", None, 32, 0, "NO", None, True),
        ("return_amount", "numeric", "YES", None, 18, 2, "NO", None, True),
        (
            "return_reason",
            "character varying",
            "YES",
            255,
            None,
            None,
            "NO",
            None,
            True,
        ),
    ),
}

EXPECTED_KEYS = {
    "sales_channels_pkey": "PRIMARY KEY (sales_channel_id)",
    "sales_channels_sales_channel_code_key": "UNIQUE (sales_channel_code)",
    "stores_pkey": "PRIMARY KEY (store_id)",
    "stores_store_code_key": "UNIQUE (store_code)",
    "customers_pkey": "PRIMARY KEY (customer_id)",
    "product_categories_pkey": "PRIMARY KEY (product_category_id)",
    "product_categories_category_code_key": "UNIQUE (category_code)",
    "products_pkey": "PRIMARY KEY (product_id)",
    "products_sku_key": "UNIQUE (sku)",
    "products_product_category_id_fkey": "FOREIGN KEY (product_category_id) REFERENCES product_categories(product_category_id)",
    "orders_pkey": "PRIMARY KEY (order_id)",
    "orders_sales_channel_id_fkey": "FOREIGN KEY (sales_channel_id) REFERENCES sales_channels(sales_channel_id)",
    "orders_store_id_fkey": "FOREIGN KEY (store_id) REFERENCES stores(store_id)",
    "orders_customer_id_fkey": "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)",
    "order_items_pkey": "PRIMARY KEY (order_item_id)",
    "uq_order_items_order_line": "UNIQUE (order_id, line_number)",
    "order_items_order_id_fkey": "FOREIGN KEY (order_id) REFERENCES orders(order_id)",
    "order_items_product_id_fkey": "FOREIGN KEY (product_id) REFERENCES products(product_id)",
    "payments_pkey": "PRIMARY KEY (payment_id)",
    "payments_order_id_fkey": "FOREIGN KEY (order_id) REFERENCES orders(order_id)",
    "returns_pkey": "PRIMARY KEY (return_id)",
    "returns_order_item_id_fkey": "FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)",
}

EXPECTED_CHECKS = {
    "ck_sales_channels_code_non_blank": "btrimsales_channel_code<>''",
    "ck_sales_channels_name_non_blank": "btrimsales_channel_name<>''",
    "ck_stores_code_non_blank": "btrimstore_code<>''",
    "ck_stores_name_non_blank": "btrimstore_name<>''",
    "ck_stores_country_code": "country_code~'^[A-Z]{2}$'",
    "ck_product_categories_code_non_blank": "btrimcategory_code<>''",
    "ck_product_categories_name_non_blank": "btrimcategory_name<>''",
    "ck_products_sku_non_blank": "btrimsku<>''",
    "ck_products_name_non_blank": "btrimproduct_name<>''",
    "ck_products_list_price_non_negative": "list_priceISNULLORlist_price>=0",
    "ck_products_unit_cost_non_negative": "unit_costISNULLORunit_cost>=0",
    "ck_products_currency_code": "currency_codeISNULLORcurrency_code~'^[A-Z]{3}$'",
    "ck_products_currency_presence": "currency_codeISNOTNULL=list_priceISNOTNULLORunit_costISNOTNULL",
    "ck_orders_currency_code": "currency_code~'^[A-Z]{3}$'",
    "ck_orders_amount_non_negative": "order_amountISNULLORorder_amount>=0",
    "ck_order_items_line_number_positive": "line_number>0",
    "ck_order_items_quantity_positive": "quantity>0",
    "ck_order_items_unit_price_non_negative": "unit_price>=0",
    "ck_order_items_discount_non_negative": "discount_amountISNULLORdiscount_amount>=0",
    "ck_order_items_line_amount_non_negative": "line_amount>=0",
    "ck_payments_status_non_blank": "btrimpayment_status<>''",
    "ck_payments_amount_non_negative": "payment_amount>=0",
    "ck_returns_quantity_positive": "return_quantity>0",
    "ck_returns_amount_non_negative": "return_amountISNULLORreturn_amount>=0",
    "ck_returns_reason_non_blank": "return_reasonISNULLORbtrimreturn_reason<>''",
}

EXPECTED_INDEXES = {
    "ix_orders_order_timestamp": ("orders", ["order_timestamp"]),
    "ix_orders_customer_id": ("orders", ["customer_id"]),
    "ix_orders_store_timestamp": ("orders", ["store_id", "order_timestamp"]),
    "ix_order_items_product_id": ("order_items", ["product_id"]),
    "ix_payments_order_id": ("payments", ["order_id"]),
    "ix_returns_order_item_id": ("returns", ["order_item_id"]),
}


def _normalize_check(expression: str) -> str:
    normalized = re.sub(r"::(?:text|numeric)", "", expression)
    normalized = re.sub(r"[\s()]", "", normalized)
    return normalized


def validate_sales_channel_reference_contract(
    connection: psycopg.Connection,
) -> None:
    """Reject any live sales-channel state other than the exact approved rows."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sales_channel_code, sales_channel_name
            FROM sales_channels
            ORDER BY sales_channel_code
            """
        )
        rows = tuple(cursor.fetchall())
    if rows != EXPECTED_SALES_CHANNELS:
        raise DatabaseContractError(
            "Database contract validation failed: sales-channel-reference-data"
        )


def validate_database_contract(connection: psycopg.Connection) -> None:
    """Reject drift from the explicit Milestone 2 physical schema contract."""
    failures: list[str] = []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = {row[0] for row in cursor.fetchall()}
        if tables != EXPECTED_TABLES:
            failures.append("tables")

        for table, expected in EXPECTED_COLUMNS.items():
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable,
                       character_maximum_length, numeric_precision, numeric_scale,
                       is_identity, identity_generation, column_default IS NULL
                FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            if tuple(cursor.fetchall()) != expected:
                failures.append(f"columns:{table}")

        cursor.execute(
            """
            SELECT constraint_name, pg_get_constraintdef(constraint_oid)
            FROM (
                SELECT key_constraint.conname AS constraint_name,
                       key_constraint.oid AS constraint_oid
                FROM pg_catalog.pg_constraint AS key_constraint
                JOIN pg_catalog.pg_class AS relation ON relation.oid = key_constraint.conrelid
                JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = ANY(%s)
                  AND key_constraint.contype IN ('p', 'u', 'f')
                  AND key_constraint.convalidated
            ) AS contract_constraints
            ORDER BY constraint_name
            """,
            (list(EXPECTED_COLUMNS),),
        )
        if dict(cursor.fetchall()) != EXPECTED_KEYS:
            failures.append("keys-and-foreign-keys")

        cursor.execute(
            """
            SELECT check_constraint.conname,
                   pg_get_expr(check_constraint.conbin, check_constraint.conrelid)
            FROM pg_catalog.pg_constraint AS check_constraint
            JOIN pg_catalog.pg_class AS relation ON relation.oid = check_constraint.conrelid
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = current_schema()
              AND relation.relname = ANY(%s)
              AND check_constraint.contype = 'c'
              AND check_constraint.convalidated
            ORDER BY check_constraint.conname
            """,
            (list(EXPECTED_COLUMNS),),
        )
        checks = {
            name: _normalize_check(expression) for name, expression in cursor.fetchall()
        }
        if checks != EXPECTED_CHECKS:
            failures.append("check-constraints")

        cursor.execute(
            """
            SELECT index_relation.relname
            FROM pg_catalog.pg_index AS index_definition
            JOIN pg_catalog.pg_class AS index_relation
              ON index_relation.oid = index_definition.indexrelid
            JOIN pg_catalog.pg_class AS table_relation
              ON table_relation.oid = index_definition.indrelid
            LEFT JOIN pg_catalog.pg_constraint AS backing_constraint
              ON backing_constraint.conindid = index_definition.indexrelid
             AND backing_constraint.contype IN ('p', 'u')
            WHERE table_relation.relname = ANY(%s)
              AND backing_constraint.oid IS NULL
            ORDER BY index_relation.relname
            """,
            (list(EXPECTED_COLUMNS),),
        )
        explicit_index_names = {row[0] for row in cursor.fetchall()}
        if explicit_index_names != set(EXPECTED_INDEXES):
            failures.append("indexes")

        cursor.execute(
            """
            SELECT index_relation.relname, table_relation.relname,
                   array_agg(column_attribute.attname ORDER BY indexed_column.ordinality)
            FROM pg_catalog.pg_index AS index_definition
            JOIN pg_catalog.pg_class AS index_relation ON index_relation.oid = index_definition.indexrelid
            JOIN pg_catalog.pg_class AS table_relation ON table_relation.oid = index_definition.indrelid
            JOIN unnest(index_definition.indkey) WITH ORDINALITY AS indexed_column(attnum, ordinality) ON true
            JOIN pg_catalog.pg_attribute AS column_attribute
              ON column_attribute.attrelid = table_relation.oid
             AND column_attribute.attnum = indexed_column.attnum
            WHERE index_relation.relname = ANY(%s)
            GROUP BY index_relation.relname, table_relation.relname
            ORDER BY index_relation.relname
            """,
            (list(EXPECTED_INDEXES),),
        )
        indexes = {name: (table, columns) for name, table, columns in cursor.fetchall()}
        if indexes != EXPECTED_INDEXES and "indexes" not in failures:
            failures.append("indexes")

    if failures:
        raise DatabaseContractError(
            "Database contract validation failed: " + ", ".join(failures)
        )
    validate_sales_channel_reference_contract(connection)
