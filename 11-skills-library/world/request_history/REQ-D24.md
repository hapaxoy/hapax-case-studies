# REQ-D24

- Received: 2026-03-24
- From: Veikko Saarela, E-commerce

## Request

> Is click and collect growing? Share of web orders by quarter since the start of FY24/25.

## Accepted query

```sql
SELECT d.fiscal_year, d.fiscal_quarter,
       COUNT(*) AS web_orders,
       SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) AS click_collect_orders,
       ROUND(100.0 * SUM(CASE WHEN o.fulfilment_type = 'click_and_collect' THEN 1 ELSE 0 END) / COUNT(*), 1) AS click_collect_share_pct
FROM fact_web_order o
JOIN dim_date d ON d.calendar_date = CAST(timezone('Europe/Helsinki', o.order_ts_utc AT TIME ZONE 'UTC') AS DATE)
WHERE o.status <> 'cancelled'
  AND d.calendar_date <= DATE '2026-01-25'          -- last complete quarter when asked (Q3 FY2025/26)
GROUP BY 1, 2
ORDER BY 1, 2;
```

## Note

Orders, not sales, so fulfilment type from fact_web_order and Helsinki order date; cancelled excluded; only quarters that were complete when asked.
