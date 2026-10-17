# REQ-D35

- Received: 2026-05-26
- From: Hanna Kivistö, Commercial (category management)

## Request

> Which 5 subcategories made the most margin in the East in the second half of last year?

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
SELECT cp.category, cp.subcategory, SUM(n.net_sales - n.cost) AS gross_margin, SUM(n.net_sales) AS net_sales
FROM net_lines n
JOIN dim_date d     ON d.calendar_date = n.business_date
JOIN dim_store cs   ON cs.store_id = n.store_id AND cs.is_current
JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE cs.region = 'East'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 7 AND 12
GROUP BY 1, 2
ORDER BY gross_margin DESC
LIMIT 5;
```

## Note

East as-is (Kouvola is no longer in it); second half = P7-P12 including week 53.
