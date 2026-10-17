-- Click-and-collect orders by collection store, with the share of all collected orders.
-- facts: DEF-CLICK-COLLECT, DEF-TIMEZONE, REG-CANCELLED, CAL-RELATIVE
-- Pattern from REQ-D23. The collection store is fact_web_order.pickup_store_key (a store version key);
-- an order counts on its dispatch (ready-for-collection) date in Helsinki time.
-- Grain of the output: store_id.
WITH params AS (
    SELECT DATE '2026-08-31' AS start_date, DATE '2026-09-27' AS end_date      -- FY2026/27 P05
),
collected AS (
    SELECT ps.store_id, ps.store_name
    FROM fact_web_order o
    JOIN dim_store ps ON ps.store_key = o.pickup_store_key
    CROSS JOIN params
    WHERE o.status = 'collected'
      AND CAST(timezone('Europe/Helsinki', o.dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE)
          BETWEEN params.start_date AND params.end_date
)
SELECT store_id, store_name, COUNT(*) AS collected_orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_collected_pct
FROM collected
GROUP BY 1, 2
ORDER BY collected_orders DESC;
