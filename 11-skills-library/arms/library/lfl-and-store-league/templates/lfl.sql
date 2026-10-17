-- Like-for-like (LFL) net sales growth, total and by region (as-is).
-- facts: DEF-LFL-BASIS, DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS, DEF-LFL-REFIT, DEF-LFL-WEEK53, TEAM-LFL-EDGE,
--        REG-REFITS, REG-STORE-EVENTS, DEF-NET-SALES, DEF-STORE-SCOPE, CAL-COMPARE, DEF-HIERARCHY-ASIS
-- Pattern from REQ-D06 to REQ-D09 (store-week list, then sales joined to it).
-- Physical stores only (store_id below 900); week 53 is never LFL (the week filter stops at 52).
-- A store-week counts when the store traded in that fiscal week in both years: open, not closed,
-- no refit week from ref_store_closure. The opening rule tests open_date against the first day of the
-- requested range minus 364 days, as the accepted queries do.
-- Edit params: the two fiscal years and the fiscal-week range (e.g. P3 = weeks 9-13).
-- Grain of the output: one total row (region NULL) plus one row per region.
WITH params AS (
    SELECT 'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year, 9 AS first_week, 13 AS last_week   -- REQ-D07: P3
),
range_start AS (
    SELECT MIN(d.calendar_date) AS first_day
    FROM dim_date d CROSS JOIN params
    WHERE d.fiscal_year = params.ty_year AND d.fiscal_week = params.first_week
),
weeks AS (
    SELECT DISTINCT d.fiscal_year, d.fiscal_week, d.fiscal_week_start_date, d.fiscal_week_end_date
    FROM dim_date d CROSS JOIN params
    WHERE d.fiscal_year IN (params.ty_year, params.ly_year)
      AND d.fiscal_week BETWEEN params.first_week AND LEAST(params.last_week, 52)    -- week 53 is never LFL
),
store_weeks AS (
    -- every store x fiscal week in the two years, flagged as trading or not (open, not closed, no refit)
    SELECT st.store_id, w.fiscal_year, w.fiscal_week,
           (st.open_date IS NULL OR st.open_date <= w.fiscal_week_start_date)
           AND (st.close_date IS NULL OR st.close_date >= w.fiscal_week_end_date)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                           WHERE c.store_id = st.store_id
                             AND c.closure_start_date <= w.fiscal_week_end_date
                             AND c.closure_end_date >= w.fiscal_week_start_date) AS trading
    FROM dim_store st
    CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
),
lfl_store_weeks AS (
    SELECT ty.store_id, ty.fiscal_week
    FROM store_weeks ty
    CROSS JOIN params
    CROSS JOIN range_start
    JOIN store_weeks ly ON ly.store_id = ty.store_id AND ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = params.ly_year
    JOIN dim_store st   ON st.store_id = ty.store_id AND st.is_current
    WHERE ty.fiscal_year = params.ty_year AND ty.trading AND ly.trading
      AND (st.open_date IS NULL OR st.open_date <= range_start.first_day - 364)   -- open 52+ weeks before the period
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
lfl_sales AS (
    SELECT d.fiscal_year, cs.region, SUM(n.net_sales) AS net_sales, COUNT(DISTINCT n.store_id || '-' || d.fiscal_week) AS store_weeks
    FROM net_lines n
    JOIN dim_date d   ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    CROSS JOIN params
    WHERE d.fiscal_year IN (params.ty_year, params.ly_year)
      AND d.fiscal_week BETWEEN params.first_week AND LEAST(params.last_week, 52)
    GROUP BY GROUPING SETS ((d.fiscal_year), (d.fiscal_year, cs.region))
)
SELECT ty.region, ty.store_weeks, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty
CROSS JOIN params
JOIN lfl_sales ly ON ly.region IS NOT DISTINCT FROM ty.region AND ly.fiscal_year = params.ly_year
WHERE ty.fiscal_year = params.ty_year
ORDER BY ty.region NULLS FIRST;
