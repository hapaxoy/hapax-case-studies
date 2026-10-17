# REQ-D31

- Received: 2025-05-14
- From: Sanna Ahonen, Marketing and CRM

## Request

> Member share of sales by month, November to April just gone

## Accepted query

```sql
WITH web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.member_key, f.net_amount
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT date_trunc('month', business_date) AS month,
       SUM(net_amount) AS net_sales,
       SUM(CASE WHEN member_key IS NOT NULL THEN net_amount ELSE 0 END) AS member_net_sales,
       ROUND(100.0 * SUM(CASE WHEN member_key IS NOT NULL THEN net_amount ELSE 0 END) / SUM(net_amount), 1) AS member_share_pct
FROM lines
WHERE business_date BETWEEN DATE '2024-11-01' AND DATE '2025-04-27'
GROUP BY 1
ORDER BY 1;
```

## Note

Net sales before returns; guest web orders and non-member receipts are the non-member part; web on dispatch date; window ends at the fiscal year end.
