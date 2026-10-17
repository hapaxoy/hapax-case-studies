# REQ-D05

- Received: 2025-06-18
- From: Leena Vuorinen, Store operations

## Request

> Regional net sales by quarter for last year, but with the regions as they were at the time. We need to match the old reports.

## Accepted query

```sql
WITH web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    -- as-was: region and format are the store version valid on the transaction date
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.region, s.format, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.region, s.format, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
by_quarter AS (
    SELECT d.fiscal_quarter, n.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE d.fiscal_year = 'FY2024/25'
    GROUP BY 1, 2
)
SELECT fiscal_quarter, region, net_sales
FROM by_quarter
ORDER BY fiscal_quarter, region;
```

## Note

As-was requested, so region is taken from the store version valid on each transaction date (four regions plus Online in FY2024/25).
