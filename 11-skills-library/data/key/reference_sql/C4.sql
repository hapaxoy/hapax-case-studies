-- C4 (pattern 3). Reference query.
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
SELECT d.fiscal_period, ROUND(SUM(n.net_sales), 2) AS garden_net_sales
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_product cp ON cp.product_key = n.product_key
WHERE d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 7 AND 12 AND cp.category = 'Garden'
GROUP BY 1 ORDER BY 1;

-- Naive variant [override] as_is_category_default: Uses today's categories (the company default) although the request asks for them as they were. The outdoor lighting range, which sold best in autumn, is missing from Garden.
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
SELECT d.fiscal_period, ROUND(SUM(n.net_sales), 2) AS garden_net_sales
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 7 AND 12 AND cp.category = 'Garden'
GROUP BY 1 ORDER BY 1;
