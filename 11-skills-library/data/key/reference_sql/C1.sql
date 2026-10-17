-- C1 (pattern 3). Reference query.
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
SELECT cp.category, ROUND(SUM(n.net_sales), 2) AS net_sales, ROUND(100.0 * SUM(n.net_sales - n.cost) / SUM(n.net_sales), 2) AS gross_margin_pct
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 6 AND cp.category IN ('Garden', 'Electrical')
GROUP BY 1 ORDER BY 1;

-- Naive variant [scd] as_was_category: Uses the category each article had on the day of sale. In period 6 the outdoor lighting range was still in Garden, so Garden is too big and Electrical too small.
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
SELECT cp.category, ROUND(SUM(n.net_sales), 2) AS net_sales, ROUND(100.0 * SUM(n.net_sales - n.cost) / SUM(n.net_sales), 2) AS gross_margin_pct
FROM net_events n JOIN dim_date d ON d.calendar_date = n.business_date JOIN dim_product cp ON cp.product_key = n.product_key
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 6 AND cp.category IN ('Garden', 'Electrical')
GROUP BY 1 ORDER BY 1;

-- Naive variant [company_definition] margin_before_returns: Counts sales and margin before returns, instead of after returns with the returned units credited back at standard cost.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT cp.category, ROUND(SUM(f.net_amount), 2) AS net_sales, ROUND(100.0 * SUM(f.net_amount - f.standard_cost) / SUM(f.net_amount), 2) AS gross_margin_pct
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
  AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 6 AND cp.category IN ('Garden', 'Electrical')
GROUP BY 1 ORDER BY 1;
