-- G1 (pattern 12). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_events AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.store_key, f.product_key, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM (SELECT * FROM fact_sales_line QUALIFY row_number() OVER (PARTITION BY receipt_id, line_no ORDER BY sales_line_id) = 1) f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, r.store_key, r.product_key, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
period_days AS (SELECT d.calendar_date, d.is_trading_day FROM dim_date d WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 5),
trading AS (
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs CROSS JOIN period_days pd
    WHERE cs.is_current AND cs.store_id < 900 AND pd.is_trading_day
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date) AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
),
sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE n.store_id < 900 AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 5
    GROUP BY 1
)
SELECT t.store_id, t.trading_days, ROUND(s.net_sales, 2) AS net_sales, ROUND(s.net_sales / t.trading_days, 2) AS net_sales_per_trading_day
FROM trading t JOIN sales s USING (store_id)
ORDER BY 4 DESC, 1;

-- Published number (same question without the repair; the problem is in no document)
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_events AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, f.store_key, f.product_key, s.store_id, p.sku,
           f.net_amount AS net_sales, f.standard_cost AS cost
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, r.store_key, r.product_key, s.store_id, p.sku, -r.refund_net, -r.standard_cost_returned
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
period_days AS (SELECT d.calendar_date, d.is_trading_day FROM dim_date d WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 5),
trading AS (
    SELECT cs.store_id, COUNT(*) AS trading_days
    FROM dim_store cs CROSS JOIN period_days pd
    WHERE cs.is_current AND cs.store_id < 900 AND pd.is_trading_day
      AND (cs.open_date IS NULL OR cs.open_date <= pd.calendar_date) AND (cs.close_date IS NULL OR cs.close_date >= pd.calendar_date)
      AND NOT EXISTS (SELECT 1 FROM ref_store_closure c WHERE c.store_id = cs.store_id AND pd.calendar_date BETWEEN c.closure_start_date AND c.closure_end_date)
    GROUP BY 1
),
sales AS (
    SELECT n.store_id, SUM(n.net_sales) AS net_sales
    FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
    WHERE n.store_id < 900 AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 5
    GROUP BY 1
)
SELECT t.store_id, t.trading_days, ROUND(s.net_sales, 2) AS net_sales, ROUND(s.net_sales / t.trading_days, 2) AS net_sales_per_trading_day
FROM trading t JOIN sales s USING (store_id)
ORDER BY 4 DESC, 1;
