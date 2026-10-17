# REQ-D32

- Received: 2026-06-09
- From: Jukka Ylönen, Marketing and CRM

## Request

> Member share of sales by region for P1 this year

## Accepted query

```sql
WITH web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, f.member_key, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT cs.region,
       SUM(l.net_amount) AS net_sales,
       ROUND(100.0 * SUM(CASE WHEN l.member_key IS NOT NULL THEN l.net_amount ELSE 0 END) / SUM(l.net_amount), 1) AS member_share_pct
FROM lines l
JOIN dim_date d   ON d.calendar_date = l.business_date
JOIN dim_store cs ON cs.store_id = l.store_id AND cs.is_current
WHERE d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 1
GROUP BY 1
ORDER BY 1;
```

## Note

Regions as-is with Online on its own line; net sales before returns.
