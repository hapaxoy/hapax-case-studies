# REQ-D37

- Received: 2025-09-09
- From: Leena Vuorinen, Store operations

## Request

> League table of the stores for P4, please

## Accepted query

```sql
WITH period_days AS (
    SELECT calendar_date FROM dim_date
    WHERE fiscal_year = 'FY2025/26' AND fiscal_period = 4 AND is_trading_day
),
trading_days AS (
    -- days the store was open: after opening, before closure, outside refit closures, not a closed holiday
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs
    CROSS JOIN period_days pd
    WHERE cs.is_current AND cs.store_id < 900
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date)
      AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c
                      WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
),
net_lines AS (
    -- physical stores only, so no web dispatch join is needed
    SELECT f.sale_date AS business_date, s.store_id, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, s.store_id, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id < 900 AND p.category <> 'ZZ Test'
),
store_sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_lines n
    JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 4
    GROUP BY 1
)
SELECT RANK() OVER (ORDER BY ss.net_sales / td.trading_days DESC) AS rank, cs.store_id, cs.store_name, cs.format,
       td.trading_days, ss.net_sales, ROUND(ss.net_sales / td.trading_days, 0) AS net_sales_per_trading_day
FROM store_sales ss
JOIN trading_days td ON td.store_id = ss.store_id
JOIN dim_store cs    ON cs.store_id = ss.store_id AND cs.is_current

ORDER BY rank;
```

## Note

Ranked on net sales per trading day, stores only (web and the training store are not stores for this).
