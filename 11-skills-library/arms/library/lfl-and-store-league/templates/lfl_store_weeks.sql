-- Which stores are in the LFL base, week by week: use it to explain an LFL figure.
-- facts: DEF-LFL-OPEN, DEF-LFL-BOTH-YEARS, DEF-LFL-REFIT, DEF-LFL-WEEK53, TEAM-LFL-EDGE, REG-REFITS, REG-STORE-EVENTS
-- Same store-week logic as lfl.sql. One row per physical store with the count of LFL weeks and the
-- weeks that dropped out, and why.
-- Grain of the output: store_id.
WITH params AS (
    SELECT 'FY2026/27' AS ty_year, 'FY2025/26' AS ly_year, 9 AS first_week, 13 AS last_week
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
      AND d.fiscal_week BETWEEN params.first_week AND LEAST(params.last_week, 52)
),
store_weeks AS (
    SELECT st.store_id, st.store_name, st.open_date, st.close_date, w.fiscal_year, w.fiscal_week,
           (st.open_date IS NULL OR st.open_date <= w.fiscal_week_start_date) AS opened,
           (st.close_date IS NULL OR st.close_date >= w.fiscal_week_end_date) AS not_closed,
           NOT EXISTS (SELECT 1 FROM ref_store_closure c
                       WHERE c.store_id = st.store_id
                         AND c.closure_start_date <= w.fiscal_week_end_date
                         AND c.closure_end_date >= w.fiscal_week_start_date) AS no_refit
    FROM dim_store st CROSS JOIN weeks w
    WHERE st.is_current AND st.store_id < 900
)
SELECT ty.store_id, ty.store_name,
       (ty.open_date IS NULL OR ty.open_date <= range_start.first_day - 364) AS open_52_weeks,
       COUNT(*) FILTER (WHERE ty.opened AND ty.not_closed AND ty.no_refit
                          AND ly.opened AND ly.not_closed AND ly.no_refit) AS weeks_trading_both_years,
       string_agg(CASE WHEN NOT (ty.no_refit AND ly.no_refit) THEN CAST(ty.fiscal_week AS VARCHAR) END, ',' ORDER BY ty.fiscal_week) AS refit_weeks,
       string_agg(CASE WHEN NOT (ty.opened AND ly.opened AND ty.not_closed AND ly.not_closed)
                       THEN CAST(ty.fiscal_week AS VARCHAR) END, ',' ORDER BY ty.fiscal_week) AS not_open_or_closed_weeks
FROM store_weeks ty
CROSS JOIN params
CROSS JOIN range_start
JOIN store_weeks ly ON ly.store_id = ty.store_id AND ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = params.ly_year
WHERE ty.fiscal_year = params.ty_year
GROUP BY ty.store_id, ty.store_name, ty.open_date, range_start.first_day
ORDER BY ty.store_id;
