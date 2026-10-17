-- V3 (pattern 14). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT d.fiscal_period, ROUND(SUM(f.gross_amount), 2) AS web_gross_incl_vat
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN web_dispatch w ON w.web_order_id = f.receipt_id JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 4 AND 6
GROUP BY 1 ORDER BY 1;

-- Naive variant [vat] flat_25_5: Multiplies web net sales by 25.5% for every period, but period 4 was entirely at 24% and period 5 was part 24%, part 25.5%.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
)
SELECT d.fiscal_period, ROUND(SUM(f.net_amount * 1.255), 2) AS web_gross_incl_vat
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN web_dispatch w ON w.web_order_id = f.receipt_id JOIN dim_date d ON d.calendar_date = w.dispatch_date
WHERE s.store_id = 900 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2024/25' AND d.fiscal_period BETWEEN 4 AND 6
GROUP BY 1 ORDER BY 1;
