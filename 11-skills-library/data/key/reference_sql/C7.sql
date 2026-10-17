-- C7 (pattern 10). Reference query.
SELECT w.closing_units FROM fact_stock_week w JOIN dim_store s ON s.store_key = w.store_key JOIN dim_product p ON p.product_key = w.product_key
WHERE s.store_id = 124 AND p.sku = 100011 AND w.week_ending_date = DATE '2026-10-04';

-- Sloppy variant 1 (must give the reference result)
SELECT w.closing_units FROM fact_stock_week w JOIN dim_store s ON s.store_key = w.store_key JOIN dim_product cp ON cp.sku = 100011 AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date WHERE s.store_id = 124 AND w.product_key IN (SELECT product_key FROM dim_product WHERE sku = 100011)
AND d.fiscal_year = 'FY2026/27' AND d.fiscal_week = 22;
