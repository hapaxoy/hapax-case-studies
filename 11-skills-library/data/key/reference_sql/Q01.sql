-- Q01 (pattern 1). Reference query.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 3 THEN 'ty' WHEN d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 3 THEN 'ly' END AS yr, cs.region AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 3) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 3)) 
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS region, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Naive variant [scd] as_was_region: Uses each store's region as it was on the day of the sale. Last year's Capital Region stores were still in South the year before, so the two years cannot be compared and the Capital Region has no comparator.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 3 THEN 'ty' WHEN d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 3 THEN 'ly' END AS yr, cs.region AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_key = n.store_key
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 3) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_quarter = 3)) 
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS region, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Naive variant [fiscal_calendar] calendar_quarter: Reads Q3 as July to September instead of the fiscal Q3 (late October to late January).
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
    SELECT CASE WHEN n.business_date BETWEEN DATE '2025-07-01' AND DATE '2025-09-30' THEN 'ty' WHEN n.business_date BETWEEN DATE '2024-07-01' AND DATE '2024-09-30' THEN 'ly' END AS yr, cs.region AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE ((n.business_date BETWEEN DATE '2025-07-01' AND DATE '2025-09-30') OR (n.business_date BETWEEN DATE '2024-07-01' AND DATE '2024-09-30')) 
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS region, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;
