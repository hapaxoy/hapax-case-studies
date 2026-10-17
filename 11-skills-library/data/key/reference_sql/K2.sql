-- K2 (pattern 6). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
web_events AS (
    SELECT w.dispatch_date AS business_date, (o.fulfilment_type = 'click_and_collect') AS is_cnc, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, (o.fulfilment_type = 'click_and_collect'), -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s ON s.store_key = r.store_key
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN e.is_cnc THEN e.net_sales ELSE 0 END) / SUM(e.net_sales), 2) AS click_collect_share_pct
FROM web_events e JOIN dim_date d ON d.calendar_date = e.business_date
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 9 AND 10
GROUP BY 1 ORDER BY 1;

-- Published number (same question without the repair; the problem is in no document)
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
web_events AS (
    SELECT w.dispatch_date AS business_date, (f.channel_id = 3) AS is_cnc, f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, (f.channel_id = 3), -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s ON s.store_key = r.store_key
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_product p ON p.product_key = f.product_key
    JOIN fact_web_order o ON o.web_order_id = f.receipt_id
    WHERE s.store_id = 900 AND p.category <> 'ZZ Test'
)
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN e.is_cnc THEN e.net_sales ELSE 0 END) / SUM(e.net_sales), 2) AS click_collect_share_pct
FROM web_events e JOIN dim_date d ON d.calendar_date = e.business_date
WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 9 AND 10
GROUP BY 1 ORDER BY 1;
