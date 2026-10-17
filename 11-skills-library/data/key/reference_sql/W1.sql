-- W1 (pattern 5). Reference query.
SELECT COUNT(*) AS web_orders FROM fact_web_order o WHERE CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE) = DATE '2025-12-01' AND o.status <> 'cancelled' AND NOT EXISTS (SELECT 1 FROM fact_sales_line tf JOIN dim_product tp ON tp.product_key = tf.product_key WHERE tf.receipt_id = o.web_order_id AND tp.category = 'ZZ Test');

-- Naive variant [time_zone] utc_day: Counts the UTC calendar day. The Cyber Monday midnight offer lands in the last hours of the previous UTC day, so orders are missing from the 1st and extra ones from the 2nd are included.
SELECT COUNT(*) AS web_orders FROM fact_web_order o WHERE CAST(o.order_ts_utc AS DATE) = DATE '2025-12-01' AND o.status <> 'cancelled' AND NOT EXISTS (SELECT 1 FROM fact_sales_line tf JOIN dim_product tp ON tp.product_key = tf.product_key WHERE tf.receipt_id = o.web_order_id AND tp.category = 'ZZ Test');
