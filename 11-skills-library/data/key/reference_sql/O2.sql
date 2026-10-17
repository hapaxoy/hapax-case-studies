-- O2 (pattern 5). Reference query.
SELECT COUNT(*) AS web_orders FROM fact_web_order o WHERE CAST(o.order_ts_utc AS DATE) = DATE '2025-11-28' AND o.status <> 'cancelled' AND NOT EXISTS (SELECT 1 FROM fact_sales_line tf JOIN dim_product tp ON tp.product_key = tf.product_key WHERE tf.receipt_id = o.web_order_id AND tp.category = 'ZZ Test');

-- Naive variant [override] helsinki_day_default: Counts the Finnish calendar day (the company default) although the request asks for the UTC day. The Black Friday midnight offer moves a few hundred orders from the 27th to the 28th.
SELECT COUNT(*) AS web_orders FROM fact_web_order o WHERE CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE) = DATE '2025-11-28' AND o.status <> 'cancelled' AND NOT EXISTS (SELECT 1 FROM fact_sales_line tf JOIN dim_product tp ON tp.product_key = tf.product_key WHERE tf.receipt_id = o.web_order_id AND tp.category = 'ZZ Test');
