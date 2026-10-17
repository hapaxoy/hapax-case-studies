-- Q03 (pattern 1). Reference query.
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
),
tagged AS (
    SELECT CASE WHEN d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2 THEN 'ty' WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 THEN 'ly' END AS yr, d.fiscal_week AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    
    WHERE ((d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2) OR (d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2)) 
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS fiscal_week, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Naive variant [fiscal_calendar] date_aligned_last_year: Compares with the same calendar dates a year earlier (1 to 28 June 2025). Last year's fiscal weeks started six days earlier, so the comparison is shifted by almost a week.
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
),
ty AS (SELECT d.fiscal_week, SUM(n.net_sales) AS v FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
       WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2 GROUP BY 1),
ly AS (SELECT d.fiscal_week, SUM(n.net_sales) AS v FROM net_events n
       JOIN dim_date d ON d.calendar_date = CAST(n.business_date + INTERVAL 1 YEAR AS DATE)
       WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 2 GROUP BY 1)
SELECT ty.fiscal_week, ROUND(ty.v, 2) AS net_sales_ty, ROUND(ly.v, 2) AS net_sales_ly, ROUND(100.0 * (ty.v / ly.v - 1), 2) AS growth_pct
FROM ty JOIN ly USING (fiscal_week) ORDER BY 1;
