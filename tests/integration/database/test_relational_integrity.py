"""Real-PostgreSQL relational and approved CHECK behavior tests."""

# ruff: noqa: E501

from datetime import UTC, datetime

import psycopg
import pytest

from sales_data_platform.database.seed import seed_sales_channels

pytestmark = pytest.mark.postgresql
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _base_rows(connection: psycopg.Connection) -> dict[str, int]:
    seed_sales_channels(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT sales_channel_id FROM sales_channels WHERE sales_channel_code='ECOMMERCE'"
        )
        channel = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO stores(store_code,store_name,country_code) VALUES('S1','Store','US') RETURNING store_id"
        )
        store = cursor.fetchone()[0]
        cursor.execute("INSERT INTO customers DEFAULT VALUES RETURNING customer_id")
        customer = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO product_categories(category_code,category_name) VALUES('C1','Category') RETURNING product_category_id"
        )
        category = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO products(sku,product_name,product_category_id) VALUES('SKU1','Product',%s) RETURNING product_id",
            (category,),
        )
        product = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orders(sales_channel_id,store_id,customer_id,order_timestamp,currency_code) VALUES(%s,%s,%s,%s,'USD') RETURNING order_id",
            (channel, store, customer, NOW),
        )
        order = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,1,%s,1,10,10) RETURNING order_item_id",
            (order, product),
        )
        item = cursor.fetchone()[0]
    return {
        "channel": channel,
        "store": store,
        "customer": customer,
        "category": category,
        "product": product,
        "order": order,
        "item": item,
    }


@pytest.mark.parametrize("case", ["channel", "store", "category", "sku", "order-line"])
def test_approved_uniqueness_is_enforced(
    contract_connection: psycopg.Connection, case: str
) -> None:
    ids = _base_rows(contract_connection)
    statements = {
        "channel": (
            "INSERT INTO sales_channels(sales_channel_code,sales_channel_name) VALUES('ECOMMERCE','Other')",
            (),
        ),
        "store": (
            "INSERT INTO stores(store_code,store_name,country_code) VALUES('S1','Other','US')",
            (),
        ),
        "category": (
            "INSERT INTO product_categories(category_code,category_name) VALUES('C1','Other')",
            (),
        ),
        "sku": (
            "INSERT INTO products(sku,product_name,product_category_id) VALUES('SKU1','Other',%s)",
            (ids["category"],),
        ),
        "order-line": (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,1,%s,1,1,1)",
            (ids["order"], ids["product"]),
        ),
    }
    with (
        pytest.raises(psycopg.errors.UniqueViolation),
        contract_connection.cursor() as cursor,
    ):
        cursor.execute(*statements[case])


@pytest.mark.parametrize(
    "case",
    [
        "product-category",
        "order-channel",
        "order-store",
        "order-customer",
        "item",
        "payment",
        "return",
    ],
)
def test_approved_foreign_keys_are_enforced(
    contract_connection: psycopg.Connection, case: str
) -> None:
    ids = _base_rows(contract_connection)
    statements = {
        "product-category": (
            "INSERT INTO products(sku,product_name,product_category_id) VALUES('BAD','Bad',999999)",
            (),
        ),
        "order-channel": (
            "INSERT INTO orders(sales_channel_id,order_timestamp,currency_code) VALUES(999999,%s,'USD')",
            (NOW,),
        ),
        "order-store": (
            "INSERT INTO orders(sales_channel_id,store_id,order_timestamp,currency_code) VALUES(%s,999999,%s,'USD')",
            (ids["channel"], NOW),
        ),
        "order-customer": (
            "INSERT INTO orders(sales_channel_id,customer_id,order_timestamp,currency_code) VALUES(%s,999999,%s,'USD')",
            (ids["channel"], NOW),
        ),
        "item": (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(999999,2,%s,1,1,1)",
            (ids["product"],),
        ),
        "payment": (
            "INSERT INTO payments(order_id,payment_timestamp,payment_status,payment_amount) VALUES(999999,%s,'PAID',1)",
            (NOW,),
        ),
        "return": (
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity) VALUES(999999,%s,1)",
            (NOW,),
        ),
    }
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation),
        contract_connection.cursor() as cursor,
    ):
        cursor.execute(*statements[case])


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            "INSERT INTO stores(store_code,store_name,country_code) VALUES('BAD','Bad','us')",
            (),
        ),
        (
            "INSERT INTO sales_channels(sales_channel_code,sales_channel_name) VALUES(' ','Bad')",
            (),
        ),
        (
            "INSERT INTO sales_channels(sales_channel_code,sales_channel_name) VALUES('BAD',' ')",
            (),
        ),
        (
            "INSERT INTO stores(store_code,store_name,country_code) VALUES(' ','Bad','US')",
            (),
        ),
        (
            "INSERT INTO stores(store_code,store_name,country_code) VALUES('S2',' ','US')",
            (),
        ),
        (
            "INSERT INTO product_categories(category_code,category_name) VALUES(' ','Bad')",
            (),
        ),
        (
            "INSERT INTO product_categories(category_code,category_name) VALUES('C2',' ')",
            (),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id) VALUES(' ','Bad',%s)",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id) VALUES('P2',' ',%s)",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id,list_price) VALUES('P2','P',%s,1)",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id,unit_cost,currency_code) VALUES('P2','P',%s,-1,'USD')",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id,list_price,currency_code) VALUES('P2','P',%s,1,'usd')",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id,currency_code) VALUES('P2','P',%s,'USD')",
            ("category",),
        ),
        (
            "INSERT INTO products(sku,product_name,product_category_id,list_price,currency_code) VALUES('P2','P',%s,-1,'USD')",
            ("category",),
        ),
        (
            "INSERT INTO orders(sales_channel_id,order_timestamp,currency_code) VALUES(%s,%s,'usd')",
            ("channel", NOW),
        ),
        (
            "INSERT INTO orders(sales_channel_id,order_timestamp,currency_code,order_amount) VALUES(%s,%s,'USD',-1)",
            ("channel", NOW),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,0,%s,1,1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,-1,%s,1,1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,2,%s,0,1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,2,%s,-1,1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,2,%s,1,-1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,discount_amount,line_amount) VALUES(%s,2,%s,1,1,-1,1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,2,%s,1,1,-1)",
            ("order", "product"),
        ),
        (
            "INSERT INTO payments(order_id,payment_timestamp,payment_status,payment_amount) VALUES(%s,%s,' ',1)",
            ("order", NOW),
        ),
        (
            "INSERT INTO payments(order_id,payment_timestamp,payment_status,payment_amount) VALUES(%s,%s,'PAID',-1)",
            ("order", NOW),
        ),
        (
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity) VALUES(%s,%s,0)",
            ("item", NOW),
        ),
        (
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity) VALUES(%s,%s,-1)",
            ("item", NOW),
        ),
        (
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity,return_amount) VALUES(%s,%s,1,-1)",
            ("item", NOW),
        ),
        (
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity,return_reason) VALUES(%s,%s,1,' ')",
            ("item", NOW),
        ),
    ],
)
def test_approved_check_constraints_are_enforced(
    contract_connection: psycopg.Connection, sql: str, params: tuple[object, ...]
) -> None:
    ids = _base_rows(contract_connection)
    resolved = tuple(
        ids[value] if isinstance(value, str) and value in ids else value
        for value in params
    )
    with (
        pytest.raises(psycopg.errors.CheckViolation),
        contract_connection.cursor() as cursor,
    ):
        cursor.execute(sql, resolved)
