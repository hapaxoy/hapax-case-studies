-- T1 (pattern 11). Reference query.
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
SELECT n.sku, ROUND(SUM(n.net_sales - n.cost), 2) AS gross_margin
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE cs.region = 'South' AND d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 4
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Naive variant [scd] as_was_region: Uses the region each store had in early 2025, so the five stores that are now the Capital Region count as South and Kouvola does not.
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
SELECT n.sku, ROUND(SUM(n.net_sales - n.cost), 2) AS gross_margin
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_key = n.store_key
WHERE cs.region = 'South' AND d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 4
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Naive variant [fiscal_calendar] calendar_quarter_four: Reads Q4 as October to December 2024 instead of the fiscal Q4 (late January to late April 2025).
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
SELECT n.sku, ROUND(SUM(n.net_sales - n.cost), 2) AS gross_margin
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE cs.region = 'South' AND n.business_date BETWEEN DATE '2024-10-01' AND DATE '2024-12-31'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;
