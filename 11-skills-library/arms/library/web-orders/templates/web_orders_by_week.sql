-- Web orders per fiscal week, counted on the Helsinki order date, cancelled orders out.
-- facts: DEF-WEB-ORDER-COUNT, DEF-WEB-CANCELLED, DEF-TIMEZONE, REG-UTC, REG-CANCELLED, DEF-CLICK-COLLECT
-- Pattern from REQ-D18 (weekly count) and REQ-D24 (click-and-collect share of orders by quarter).
-- Processing orders count; cancelled ones do not. Orders come from fact_web_order (one row per order),
-- not from sales lines, so processing orders without lines are still counted.
-- Grain of the output: fiscal_week.
WITH params AS (
    SELECT 'FY2025/26' AS fiscal_year, 8 AS fiscal_period      -- REQ-D18: P8
)
SELECT d.fiscal_week,
       COUNT(*) AS web_orders,
       COUNT(*) FILTER (WHERE o.fulfilment_type = 'click_and_collect') AS click_collect_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE o.fulfilment_type = 'click_and_collect') / COUNT(*), 1) AS click_collect_share_pct
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
CROSS JOIN params
WHERE d.fiscal_year = params.fiscal_year AND d.fiscal_period = params.fiscal_period
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
