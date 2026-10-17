-- AT (pattern 7). Reference query.
SELECT s.format, ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id < 900 AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4
GROUP BY 1 ORDER BY 1;

-- Naive variant [exclusions] no_store_scope: Does not limit the table to the physical stores, so the web shop shows up as a 'Web' format and the training store as its own line.
SELECT s.format, ROUND(SUM(f.net_amount) / COUNT(DISTINCT f.receipt_id), 2) AS atv
FROM fact_sales_line f
JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE TRUE AND NOT f.staff_purchase_flag AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4
GROUP BY 1 ORDER BY 1;
