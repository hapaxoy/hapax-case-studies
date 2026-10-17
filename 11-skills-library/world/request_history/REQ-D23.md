# REQ-D23

- Received: 2026-10-01
- From: Mika Hietala, Store operations

## Request

> Which stores handled the most click and collect orders last period, and what share of all collected orders is that

## Accepted query

```sql
WITH collected AS (
    SELECT ps.store_id, ps.store_name
    FROM fact_web_order o
    JOIN dim_store ps ON ps.store_key = o.pickup_store_key
    WHERE o.status = 'collected'
      AND CAST(timezone('Europe/Helsinki', o.dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE)
          BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'                       -- FY2026/27 P5
)
SELECT store_id, store_name, COUNT(*) AS collected_orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_of_collected_pct
FROM collected
GROUP BY 1, 2
ORDER BY collected_orders DESC
LIMIT 15;
```

## Note

Last completed period is P5 (31 Aug - 27 Sep 2026); an order counts on its dispatch (ready-for-collection) date in Helsinki time.
