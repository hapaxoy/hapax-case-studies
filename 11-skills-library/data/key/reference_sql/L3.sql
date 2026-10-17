-- L3 (pattern 2). Reference query.
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
weeks AS (
    SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date AS ws, fiscal_week_end_date AS we,
           MIN(fiscal_week_start_date) OVER (PARTITION BY fiscal_year, fiscal_period) AS pstart
    FROM dim_date WHERE fiscal_year IN ('FY2025/26', 'FY2024/25') AND fiscal_week BETWEEN 27 AND 39
),
store_week AS (
    -- trading = open for the whole week, not closed, not in a refit
    SELECT st.store_id, w.fiscal_year, w.fiscal_week, w.pstart,
           (st.open_date IS NULL OR st.open_date <= w.ws) AND (st.close_date IS NULL OR st.close_date >= w.we)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = st.store_id
                           AND c.closure_start_date <= w.we AND c.closure_end_date >= w.ws) AS trading
    FROM dim_store st CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
),
eligible AS (
    SELECT t.store_id, t.fiscal_week
    FROM store_week t
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = 'FY2024/25'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = 'FY2025/26' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2025-10-27' - 364)
),
tagged AS (
    SELECT CASE WHEN (d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week
    WHERE n.store_id < 900 AND ((d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_week BETWEEN 27 AND 39))
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current
GROUP BY 1 ORDER BY 1;

-- Also accepted: the 364-day rule applied to the first day of each fiscal period (Lohja counts from P8)
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
weeks AS (
    SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date AS ws, fiscal_week_end_date AS we,
           MIN(fiscal_week_start_date) OVER (PARTITION BY fiscal_year, fiscal_period) AS pstart
    FROM dim_date WHERE fiscal_year IN ('FY2025/26', 'FY2024/25') AND fiscal_week BETWEEN 27 AND 39
),
store_week AS (
    -- trading = open for the whole week, not closed, not in a refit
    SELECT st.store_id, w.fiscal_year, w.fiscal_week, w.pstart,
           (st.open_date IS NULL OR st.open_date <= w.ws) AND (st.close_date IS NULL OR st.close_date >= w.we)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = st.store_id
                           AND c.closure_start_date <= w.we AND c.closure_end_date >= w.ws) AS trading
    FROM dim_store st CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
),
eligible AS (
    SELECT t.store_id, t.fiscal_week
    FROM store_week t
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = 'FY2024/25'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = 'FY2025/26' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= t.pstart - 364)
),
tagged AS (
    SELECT CASE WHEN (d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week
    WHERE n.store_id < 900 AND ((d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_week BETWEEN 27 AND 39))
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current
GROUP BY 1 ORDER BY 1;

-- Naive variant [scd] as_was_region: Uses each year's own regions. The Capital Region did not exist the year before, so there is nothing to compare it with, and South and East are different sets of stores in the two years.
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
weeks AS (
    SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date AS ws, fiscal_week_end_date AS we,
           MIN(fiscal_week_start_date) OVER (PARTITION BY fiscal_year, fiscal_period) AS pstart
    FROM dim_date WHERE fiscal_year IN ('FY2025/26', 'FY2024/25') AND fiscal_week BETWEEN 27 AND 39
),
store_week AS (
    -- trading = open for the whole week, not closed, not in a refit
    SELECT st.store_id, w.fiscal_year, w.fiscal_week, w.pstart,
           (st.open_date IS NULL OR st.open_date <= w.ws) AND (st.close_date IS NULL OR st.close_date >= w.we)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = st.store_id
                           AND c.closure_start_date <= w.we AND c.closure_end_date >= w.ws) AS trading
    FROM dim_store st CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
),
eligible AS (
    SELECT t.store_id, t.fiscal_week
    FROM store_week t
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = 'FY2024/25'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = 'FY2025/26' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2025-10-27' - 364)
),
tagged AS (
    SELECT CASE WHEN (d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week
    WHERE n.store_id < 900 AND ((d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 27 AND 39) OR (d.fiscal_year = 'FY2024/25' AND d.fiscal_week BETWEEN 27 AND 39))
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_key = t.store_key
GROUP BY 1 ORDER BY 1;

-- Naive variant [company_definition] all_stores_no_lfl_rules: Compares every physical store with no LFL rules, so Lohja (open less than a year) and Savonlinna's partial year are in the base.
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
    SELECT CASE WHEN d.fiscal_year = 'FY2025/26' THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.net_sales AS v
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE n.store_id < 900 AND d.fiscal_year IN ('FY2025/26', 'FY2024/25') AND d.fiscal_week BETWEEN 27 AND 39
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly,
       ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current
GROUP BY 1 ORDER BY 1;
