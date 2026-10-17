# REQ-D17

- Received: 2025-12-03
- From: Tiina Mäkelä, E-commerce

## Request

> Daily web sales for Black Friday week please

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
)
SELECT n.business_date, SUM(n.net_sales) AS web_net_sales
FROM net_lines n
WHERE n.store_id = 900
  AND n.business_date BETWEEN DATE '2025-11-24' AND DATE '2025-11-30'    -- Mon-Sun of Black Friday week 2025
GROUP BY 1
ORDER BY 1;
```

## Note

Web sales on the Helsinki dispatch date (not the order date, not UTC), returns booked to the web shop on their own date.
