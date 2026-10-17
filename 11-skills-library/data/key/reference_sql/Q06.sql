-- Q06 (pattern 1). Reference query.
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
SELECT cs.region, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1 ORDER BY metric_value DESC;

-- Accepted reading: Rank by net sales, year to date
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
SELECT cs.region, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1 ORDER BY metric_value DESC;

-- Accepted reading: Rank by gross margin percentage, year to date
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
SELECT cs.region, ROUND(100.0 * SUM(n.net_sales - n.cost) / SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22
GROUP BY 1 ORDER BY metric_value DESC;

-- Accepted reading: Rank by net sales growth against last year, year to date (week for week, weeks 1 to 22 of both years)
SELECT region, growth_pct AS metric_value FROM (WITH web_dispatch AS (
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
),
tagged AS (
    SELECT CASE WHEN d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22 THEN 'ty' WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_week <= 22 THEN 'ly' END AS yr, cs.region AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE ((d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22) OR (d.fiscal_year = 'FY2025/26' AND d.fiscal_week <= 22)) AND n.store_id < 900
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS region, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1) ORDER BY metric_value DESC, region;

-- Same reading on the published data (accepted with a caveat naming the duplicated receipts): growth_total
SELECT region, growth_pct AS metric_value FROM (WITH web_dispatch AS (
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
    SELECT CASE WHEN d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22 THEN 'ty' WHEN d.fiscal_year = 'FY2025/26' AND d.fiscal_week <= 22 THEN 'ly' END AS yr, cs.region AS grp, n.net_sales AS v
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE ((d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 22) OR (d.fiscal_year = 'FY2025/26' AND d.fiscal_week <= 22)) AND n.store_id < 900
),
agg AS (SELECT yr, grp, SUM(v) AS v FROM tagged GROUP BY 1, 2)
SELECT COALESCE(t.grp, l.grp) AS region, ROUND(t.v, 2) AS net_sales_ty, ROUND(l.v, 2) AS net_sales_ly,
       ROUND(100.0 * (t.v / l.v - 1), 2) AS growth_pct
FROM (SELECT * FROM agg WHERE yr = 'ty') t
FULL OUTER JOIN (SELECT * FROM agg WHERE yr = 'ly') l ON t.grp = l.grp
ORDER BY 1) ORDER BY metric_value DESC, region;

-- Accepted reading: Rank by like-for-like growth against last year, year to date
SELECT region, lfl_growth_pct AS metric_value FROM (WITH web_dispatch AS (
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
),
weeks AS (
    SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date AS ws, fiscal_week_end_date AS we,
           MIN(fiscal_week_start_date) OVER (PARTITION BY fiscal_year, fiscal_period) AS pstart
    FROM dim_date WHERE fiscal_year IN ('FY2026/27', 'FY2025/26') AND fiscal_week BETWEEN 1 AND 22
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
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = 'FY2025/26'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = 'FY2026/27' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2026-05-04' - 364)
),
tagged AS (
    SELECT CASE WHEN (d.fiscal_year = 'FY2026/27' AND d.fiscal_week BETWEEN 1 AND 22) THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week
    WHERE n.store_id < 900 AND ((d.fiscal_year = 'FY2026/27' AND d.fiscal_week BETWEEN 1 AND 22) OR (d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 1 AND 22))
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current
GROUP BY 1 ORDER BY 1) ORDER BY metric_value DESC, region;

-- Same reading on the published data (accepted with a caveat naming the duplicated receipts): growth_lfl
SELECT region, lfl_growth_pct AS metric_value FROM (WITH web_dispatch AS (
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
    FROM dim_date WHERE fiscal_year IN ('FY2026/27', 'FY2025/26') AND fiscal_week BETWEEN 1 AND 22
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
    JOIN store_week l ON l.store_id = t.store_id AND l.fiscal_week = t.fiscal_week AND l.fiscal_year = 'FY2025/26'
    JOIN dim_store st ON st.store_id = t.store_id AND st.is_current
    WHERE t.fiscal_year = 'FY2026/27' AND t.trading AND l.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2026-05-04' - 364)
),
tagged AS (
    SELECT CASE WHEN (d.fiscal_year = 'FY2026/27' AND d.fiscal_week BETWEEN 1 AND 22) THEN 'ty' ELSE 'ly' END AS yr, n.store_id, n.store_key, n.net_sales AS v, d.fiscal_week
    FROM net_events n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN eligible el ON el.store_id = n.store_id AND el.fiscal_week = d.fiscal_week
    WHERE n.store_id < 900 AND ((d.fiscal_year = 'FY2026/27' AND d.fiscal_week BETWEEN 1 AND 22) OR (d.fiscal_year = 'FY2025/26' AND d.fiscal_week BETWEEN 1 AND 22))
)
SELECT cs.region AS region, ROUND(SUM(CASE WHEN yr = 'ty' THEN v END), 2) AS net_sales_ty, ROUND(SUM(CASE WHEN yr = 'ly' THEN v END), 2) AS net_sales_ly, ROUND(100.0 * (SUM(CASE WHEN yr = 'ty' THEN v END) / SUM(CASE WHEN yr = 'ly' THEN v END) - 1), 2) AS lfl_growth_pct
FROM tagged t JOIN dim_store cs ON cs.store_id = t.store_id AND cs.is_current
GROUP BY 1 ORDER BY 1) ORDER BY metric_value DESC, region;

-- Naive variant [fiscal_calendar] ytd_to_last_period: Stops the year to date at the end of period 5 (week 21) instead of the last completed week (week 22).
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
SELECT cs.region, ROUND(SUM(n.net_sales), 2) AS metric_value
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
WHERE n.store_id < 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week <= 21
GROUP BY 1 ORDER BY metric_value DESC;
