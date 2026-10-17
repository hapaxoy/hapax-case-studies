# REQ-D21

- Received: 2026-09-03
- From: Tiina Mäkelä, E-commerce

## Request

> Web sales by category for P4, plus what share of web each one is

## Accepted query

```sql
WITH web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    -- sales: stores on the sale date, web on the Helsinki dispatch date
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    -- returns reduce net sales on the return date
    SELECT r.return_date, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
by_category AS (
    SELECT cp.category, SUM(n.net_sales) AS web_net_sales
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    WHERE n.store_id = 900 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4
    GROUP BY 1
)
SELECT category, web_net_sales, ROUND(100.0 * web_net_sales / SUM(web_net_sales) OVER (), 1) AS share_of_web_pct
FROM by_category
ORDER BY web_net_sales DESC;
```

## Note

P4 = current year's P4; web sales on dispatch date, categories as-is.
