-- T2 (pattern 11). Reference query.
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Most units sold
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Highest net sales
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
SELECT n.sku, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Most units sold, web units dated by dispatch date
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Most units sold in the stores only
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5 AND s.store_id < 900
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Naive variant [fiscal_calendar] partial_period_6: Takes 'last period' as P6, the period that has only one week loaded so far, instead of the last completed period, P5.
SELECT p.sku, SUM(f.quantity) AS metric_value
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 6
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;
