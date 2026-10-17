# REQ-D15

- Received: 2025-09-24
- From: Pekka Lindroos, Commercial (category management)

## Request

> Furniture return rate by subcategory, FY24/25 sales

## Accepted query

```sql
WITH sold AS (
    SELECT cp.subcategory, SUM(f.net_amount) AS sold_net
    
    FROM fact_sales_line f
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2024/25' AND cp.category = 'Furniture'
    GROUP BY 1
),
returned AS (
    SELECT cp.subcategory, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s     ON s.store_key = f.store_key
    JOIN dim_product p   ON p.product_key = f.product_key
    JOIN dim_product cp  ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d      ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
      AND d.fiscal_year = 'FY2024/25' AND cp.category = 'Furniture'
    GROUP BY 1
)
SELECT sold.subcategory, sold.sold_net, COALESCE(returned.returned_net, 0) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (subcategory)
ORDER BY sold.subcategory;
```

## Note

Cohort = FY2024/25 sales, all returns attributed back to the sale; Furniture as-is.
