-- T5 (pattern 11). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_events AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.store_key, f.product_key, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, r.store_key, r.product_key, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT n.sku, ROUND(SUM(n.net_sales), 2) AS web_net_sales
FROM net_events n
WHERE n.store_id = 900 AND n.business_date >= DATE '2025-11-03'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Naive variant [migration] channel_code_filter: Filters on channel_code = 'WB', which is empty from the migration date, so the result is empty.
SELECT p.sku, ROUND(SUM(f.net_amount), 2) AS web_net_sales
FROM fact_sales_line f JOIN dim_product p ON p.product_key = f.product_key
WHERE f.channel_code = 'WB' AND f.sale_date >= DATE '2025-11-03'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;
