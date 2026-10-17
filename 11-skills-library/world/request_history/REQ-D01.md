# REQ-D01

- Received: 2025-12-02
- From: Marjatta Salonen, Finance (FP&A)

## Request

> Hi, can I get weekly net sales by region for P6, this year against last year? For the board pack, thanks.

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
weekly AS (
    SELECT d.fiscal_year, d.fiscal_week, cs.region, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d  ON d.calendar_date = n.business_date
    JOIN dim_store cs ON cs.store_id = n.store_id AND cs.is_current
    WHERE d.fiscal_period = 6 AND d.fiscal_year IN ('FY2025/26', 'FY2024/25')
    GROUP BY 1, 2, 3
)
SELECT ty.fiscal_week, ty.region, ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 1) AS growth_pct
FROM weekly ty
JOIN weekly ly ON ly.fiscal_week = ty.fiscal_week AND ly.region = ty.region AND ly.fiscal_year = 'FY2024/25'
WHERE ty.fiscal_year = 'FY2025/26'
ORDER BY ty.fiscal_week, ty.region;
```

## Note

As-is regions (current hierarchy restated), Online shown as its own line, weeks lined up by fiscal week number.
