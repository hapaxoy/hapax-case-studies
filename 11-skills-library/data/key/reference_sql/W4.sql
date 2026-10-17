-- W4 (pattern 5). Reference query.
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
)
SELECT d.fiscal_period, ROUND(SUM(n.net_sales), 2) AS web_net_sales
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date
WHERE n.store_id = 900 AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;

-- Naive variant [migration] legacy_view: Reads the old reporting view rpt.v_daily_sales, which stops showing web sales on 3 November 2025. Period 7 is short and periods 8 and 9 show nothing.
SELECT d.fiscal_period, ROUND(SUM(v.net_sales), 2) AS web_net_sales
FROM rpt.v_daily_sales v JOIN dim_date d ON d.calendar_date = v.sale_date
WHERE v.channel = 'WB' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;

-- Naive variant [migration] channel_code_filter: Filters on channel_code = 'WB', a column that is no longer filled after the migration, so web sales vanish from 3 November.
SELECT d.fiscal_period, ROUND(SUM(f.net_amount), 2) AS web_net_sales
FROM fact_sales_line f JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE f.channel_code = 'WB' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 5 AND 8
GROUP BY 1 ORDER BY 1;
