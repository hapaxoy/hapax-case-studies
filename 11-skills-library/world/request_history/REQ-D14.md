# REQ-D14

- Received: 2026-03-10
- From: Hanna Kivistö, Commercial (category management)

## Request

> Return rate by category for goods sold in the first four periods of last year.

## Accepted query

```sql
WITH sold AS (
    SELECT cp.category, SUM(f.net_amount) AS sold_net
    
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 4
    GROUP BY 1
),
returned AS (
    -- cohort by the original sale, whenever the return happened
    SELECT cp.category, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 1 AND 4
    GROUP BY 1
)
SELECT sold.category, sold.sold_net, COALESCE(returned.returned_net, 0) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (category)
ORDER BY return_rate_pct DESC;
```

## Note

Sale-week cohort: refunds are matched to the week the item was sold, not the week it came back; cohort is old enough to be complete.
