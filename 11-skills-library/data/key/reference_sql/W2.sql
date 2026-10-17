-- W2 (pattern 5). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
events AS (
    SELECT w.dispatch_date AS business_date, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, -r.refund_net
    FROM fact_return_line r JOIN dim_store s ON s.store_key = r.store_key JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT business_date, ROUND(SUM(net_sales), 2) AS web_net_sales FROM events
WHERE business_date BETWEEN DATE '2025-12-15' AND DATE '2025-12-23'
GROUP BY 1 ORDER BY 1;

-- Naive variant [time_zone] utc_dispatch_day: Uses the UTC date of the dispatch time. Carrier hand-over scans after 21:00 UTC (midnight in Finland) fall on the next Finnish day and are put on the wrong one.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
events AS (
    SELECT CAST(o.dispatch_ts_utc AS DATE) AS business_date, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, -r.refund_net
    FROM fact_return_line r JOIN dim_store s ON s.store_key = r.store_key JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT business_date, ROUND(SUM(net_sales), 2) AS web_net_sales FROM events
WHERE business_date BETWEEN DATE '2025-12-15' AND DATE '2025-12-23'
GROUP BY 1 ORDER BY 1;

-- Naive variant [time_zone] order_date_not_dispatch: Puts each sale on the day the order was placed instead of the day it was dispatched.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
events AS (
    SELECT f.sale_date AS business_date, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, -r.refund_net
    FROM fact_return_line r JOIN dim_store s ON s.store_key = r.store_key JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT business_date, ROUND(SUM(net_sales), 2) AS web_net_sales FROM events
WHERE business_date BETWEEN DATE '2025-12-15' AND DATE '2025-12-23'
GROUP BY 1 ORDER BY 1;
