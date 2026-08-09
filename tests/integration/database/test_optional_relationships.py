"""Real-PostgreSQL tests protecting approved optional cardinalities."""

# ruff: noqa: E501

from datetime import UTC, datetime

import psycopg
import pytest

from sales_data_platform.database.seed import seed_sales_channels

pytestmark = pytest.mark.postgresql


def test_optional_order_payment_and_return_relationships(
    contract_connection: psycopg.Connection,
) -> None:
    seed_sales_channels(contract_connection)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    with contract_connection.cursor() as cursor:
        cursor.execute(
            "SELECT sales_channel_id FROM sales_channels WHERE sales_channel_code='ECOMMERCE'"
        )
        channel = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO orders(sales_channel_id,store_id,customer_id,order_timestamp,currency_code) VALUES(%s,NULL,NULL,%s,'USD') RETURNING order_id",
            (channel, timestamp),
        )
        order = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM payments WHERE order_id=%s", (order,))
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "INSERT INTO product_categories(category_code,category_name) VALUES('C1','Category') RETURNING product_category_id"
        )
        category = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO products(sku,product_name,product_category_id) VALUES('P1','Product',%s) RETURNING product_id",
            (category,),
        )
        product = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO order_items(order_id,line_number,product_id,quantity,unit_price,line_amount) VALUES(%s,1,%s,1,10,10) RETURNING order_item_id",
            (order, product),
        )
        item = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM returns WHERE order_item_id=%s", (item,))
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "INSERT INTO payments(order_id,payment_timestamp,payment_status,payment_amount) VALUES(%s,%s,'PARTIAL',5),(%s,%s,'PAID',5)",
            (order, timestamp, order, timestamp),
        )
        cursor.execute(
            "INSERT INTO returns(order_item_id,return_timestamp,return_quantity,return_amount) VALUES(%s,%s,1,5),(%s,%s,1,5)",
            (item, timestamp, item, timestamp),
        )
        cursor.execute("SELECT count(*) FROM payments WHERE order_id=%s", (order,))
        assert cursor.fetchone() == (2,)
        cursor.execute("SELECT count(*) FROM returns WHERE order_item_id=%s", (item,))
        assert cursor.fetchone() == (2,)
