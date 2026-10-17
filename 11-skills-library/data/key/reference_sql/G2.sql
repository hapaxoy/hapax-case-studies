-- G2 (pattern 12). Reference query.
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Highest net sales this year to date
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Largest sales area (square metres)
SELECT store_id, sqm AS metric_value FROM dim_store WHERE is_current AND store_id < 900 AND close_date IS NULL
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Highest net sales over the last full fiscal year (FY2025/26)
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_events AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.store_key, f.product_key, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM (SELECT * FROM fact_sales_line QUALIFY row_number() OVER (PARTITION BY receipt_id, line_no ORDER BY sales_line_id) = 1) f
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2025/26'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Same reading on the published data (accepted with a caveat naming the duplicated receipts): net_sales_last_fiscal_year
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2025/26'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Accepted reading: Highest net sales over the trailing 52 weeks (5 October 2025 to 4 October 2026)
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id < 900 AND n.business_date BETWEEN DATE '2025-10-05' AND DATE '2026-10-04'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;

-- Naive variant [exclusions] web_shop_ranked_as_store: Ranks the web shop (store 900) alongside the physical stores, and it comes first.
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
SELECT n.store_id, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 10;
