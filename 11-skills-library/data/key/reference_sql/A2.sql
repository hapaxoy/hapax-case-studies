-- A2 (pattern 7). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test' 
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period BETWEEN 1 AND 3;

-- Naive variant [override] stores_only_default: Leaves the web orders out (the company default) although the request asks for them. Web orders are larger than store receipts, so the figure is too low.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
JOIN dim_date d ON d.calendar_date = COALESCE(w.dispatch_date, f.sale_date)
WHERE s.store_id <> 999 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test' AND s.store_id < 900
  AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period BETWEEN 1 AND 3;
