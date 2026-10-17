-- U2 (pattern 8). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN COALESCE(f.member_key, o.member_key) IS NOT NULL THEN f.net_amount ELSE 0 END) / SUM(f.net_amount), 2) AS member_share_pct
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 9 AND 11
GROUP BY 1 ORDER BY 1;

-- Published number (same question without the repair; the problem is in no document)
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT d.fiscal_period,
       ROUND(100.0 * SUM(CASE WHEN f.member_key IS NOT NULL THEN f.net_amount ELSE 0 END) / SUM(f.net_amount), 2) AS member_share_pct
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN fact_web_order o ON o.web_order_id = f.receipt_id JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period BETWEEN 9 AND 11
GROUP BY 1 ORDER BY 1;
