CREATE INDEX ix_orders_order_timestamp ON orders (order_timestamp);
CREATE INDEX ix_orders_customer_id ON orders (customer_id);
CREATE INDEX ix_orders_store_timestamp ON orders (store_id, order_timestamp);
CREATE INDEX ix_order_items_product_id ON order_items (product_id);
CREATE INDEX ix_payments_order_id ON payments (order_id);
CREATE INDEX ix_returns_order_item_id ON returns (order_item_id);
