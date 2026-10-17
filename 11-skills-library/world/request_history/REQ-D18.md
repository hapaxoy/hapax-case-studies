# REQ-D18

- Received: 2026-01-13
- From: Veikko Saarela, E-commerce

## Request

> How many web orders per week in P8? Not counting cancelled ones.

## Accepted query

```sql
SELECT d.fiscal_week, COUNT(*) AS web_orders
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 8
  AND o.status <> 'cancelled'
GROUP BY 1
ORDER BY 1;
```

## Note

Orders counted on the Helsinki order date; processing orders count, cancelled do not.
