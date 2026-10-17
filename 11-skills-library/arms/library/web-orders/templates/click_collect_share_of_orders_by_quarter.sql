-- Click-and-collect share of web orders by fiscal quarter, up to the last quarter complete when asked.
-- facts: DEF-CLICK-COLLECT, DEF-WEB-ORDER-COUNT, DEF-WEB-CANCELLED, DEF-TIMEZONE, CAL-RELATIVE, CAL-DATA-THROUGH
-- Pattern from REQ-D24 (asked 24 March 2026; stopped at FY2025/26 Q3, ended 25 January 2026).
-- Orders counted on the Helsinki order date, cancelled orders out. The series stops at the last quarter whose
-- end date is on or before the request date and that is fully loaded; a part quarter is not shown.
-- Edit params: request_date = the date the request was received.
-- Grain of the output: fiscal_year x fiscal_quarter.
WITH params AS (
    SELECT DATE '2026-03-24' AS request_date
),
cutoff AS (
    -- last day of the last complete quarter (quarters end with P3, P6, P9, P12)
    SELECT MAX(c.period_end_date) AS last_day
    FROM ref_fiscal_calendar c CROSS JOIN params
    WHERE c.fiscal_period IN (3, 6, 9, 12)
      AND c.period_end_date <= params.request_date
      AND c.fully_loaded
)
SELECT d.fiscal_year, d.fiscal_quarter,
       COUNT(*) AS web_orders,
       SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) AS click_collect_orders,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_collect_share_pct
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
CROSS JOIN cutoff
WHERE o.status <> 'cancelled'
  AND d.calendar_date <= cutoff.last_day
GROUP BY 1, 2
ORDER BY 1, 2;
