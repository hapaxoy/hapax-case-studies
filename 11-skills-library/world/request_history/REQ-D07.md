# REQ-D07

- Received: 2026-08-11
- From: Marjatta Salonen, Finance (FP&A)

## Request

> LFL for P3 this year. I know Kuopio was shut for the refit so please do it the usual way.

## Accepted query

```sql
WITH store_weeks AS (
    -- every store x fiscal week in the two years, flagged as trading or not (open, not closed, no refit)
    SELECT st.store_id, d.fiscal_year, d.fiscal_week,
           (st.open_date IS NULL OR st.open_date <= d.fiscal_week_start_date)
           AND (st.close_date IS NULL OR st.close_date >= d.fiscal_week_end_date)
           AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                           WHERE c.store_id = st.store_id
                             AND c.closure_start_date <= d.fiscal_week_end_date
                             AND c.closure_end_date >= d.fiscal_week_start_date) AS trading
    FROM dim_store st
    CROSS JOIN (SELECT DISTINCT fiscal_year, fiscal_week, fiscal_week_start_date, fiscal_week_end_date
                FROM dim_date
                WHERE fiscal_year IN ('FY2025/26', 'FY2026/27') AND fiscal_week BETWEEN 9 AND 13) d
    WHERE st.is_current AND st.store_id < 900
),
lfl_store_weeks AS (
    SELECT ty.store_id, ty.fiscal_week
    FROM store_weeks ty
    JOIN store_weeks ly ON ly.store_id = ty.store_id AND ly.fiscal_week = ty.fiscal_week AND ly.fiscal_year = 'FY2025/26'
    JOIN dim_store st   ON st.store_id = ty.store_id AND st.is_current
    WHERE ty.fiscal_year = 'FY2026/27' AND ty.trading AND ly.trading
      AND (st.open_date IS NULL OR st.open_date <= DATE '2026-06-29' - 364)   -- open 52+ weeks before the period
),
web_dispatch AS (
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
lfl_sales AS (
    SELECT d.fiscal_year, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    JOIN lfl_store_weeks l ON l.store_id = n.store_id AND l.fiscal_week = d.fiscal_week
    WHERE d.fiscal_year IN ('FY2026/27', 'FY2025/26') AND d.fiscal_week BETWEEN 9 AND 13
    GROUP BY 1
)
SELECT ty.net_sales AS this_year, ly.net_sales AS last_year,
       ROUND(100.0 * (ty.net_sales / ly.net_sales - 1), 2) AS lfl_growth_pct
FROM lfl_sales ty, lfl_sales ly
WHERE ty.fiscal_year = 'FY2026/27' AND ly.fiscal_year = 'FY2025/26';
```

## Note

P3 = weeks 9-13; Kuopio is in only for week 13 and Savonlinna is out (closed), both from the store-week list.
