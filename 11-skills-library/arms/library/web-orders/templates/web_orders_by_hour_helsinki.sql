-- Web orders by hour of a day, Helsinki time.
-- facts: DEF-TIMEZONE, REG-UTC, DEF-WEB-ORDER-COUNT, DEF-WEB-CANCELLED
-- Pattern from REQ-D20 (Black Friday 2024 was 29 November). Timestamps are UTC: convert to Helsinki
-- time before reading the day or the hour. Finland is UTC+2 in winter and UTC+3 in summer.
-- Grain of the output: hour_helsinki.
WITH params AS (
    SELECT DATE '2024-11-29' AS order_date
)
SELECT hour(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC')) AS hour_helsinki,
       COUNT(*) AS web_orders
FROM fact_web_order o CROSS JOIN params
WHERE CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE) = params.order_date
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
