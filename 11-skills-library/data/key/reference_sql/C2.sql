-- C2 (pattern 3). Reference query.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8 THEN 'ty' WHEN d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8 THEN 'ly' END AS yr, cp.category AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8)) AND cp.category IN ('Garden', 'Electrical')
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS category, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Also accepted: the whole Outdoor Lighting subcategory counted in Electrical, including the five delisted articles that never got a new version
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8 THEN 'ty' WHEN d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8 THEN 'ly' END AS yr, CASE WHEN cp.subcategory = 'Outdoor Lighting' THEN 'Electrical' ELSE cp.category END AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8)) AND (CASE WHEN cp.subcategory = 'Outdoor Lighting' THEN 'Electrical' ELSE cp.category END) IN ('Garden', 'Electrical')
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS category, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Naive variant [scd] as_was_category: Uses the category on the day of sale, so the outdoor lighting range sits in Garden in the year before and in Electrical last year. Both categories then show a false jump or fall.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8 THEN 'ty' WHEN d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8 THEN 'ly' END AS yr, cp.category AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.product_key = n.product_key
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_period = 8)) AND cp.category IN ('Garden', 'Electrical')
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS category, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;

-- Naive variant [fiscal_calendar] date_aligned_last_year: Compares with 24 November to 21 December 2024, one day off the fiscal period, which moves the big pre-Christmas days in or out.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8 THEN 'ty' WHEN n.business_date BETWEEN DATE '2024-11-24' AND DATE '2024-12-21' THEN 'ly' END AS yr, cp.category AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE ((d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8) OR (n.business_date BETWEEN DATE '2024-11-24' AND DATE '2024-12-21')) AND cp.category IN ('Garden', 'Electrical')
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS category, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1;
