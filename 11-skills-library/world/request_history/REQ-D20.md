# REQ-D20

- Received: 2024-12-04
- From: Veikko Saarela, E-commerce

## Request

> Web orders by hour on Black Friday, Finnish time. The midnight deal, how big was it?

## Accepted query

```sql
SELECT hour(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC')) AS hour_helsinki,
       COUNT(*) AS web_orders
FROM fact_web_order o
WHERE CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE) = DATE '2024-11-29'
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
```

## Note

Black Friday 2024 was 29 November; timestamps are UTC so they are converted to Helsinki time before the day and hour are read.
