-- C14 (pattern 11). Reference query.
SELECT cp.subcategory, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 118 AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 5
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 3;

-- Sloppy variant 1 (must give the reference result)
SELECT p.subcategory, SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key AND s.store_id = 118 JOIN dim_product p ON p.product_key = f.product_key
WHERE f.sale_date BETWEEN DATE '2026-08-31' AND DATE '2026-09-27'
GROUP BY 1
ORDER BY 2 DESC, 1
LIMIT 3;
