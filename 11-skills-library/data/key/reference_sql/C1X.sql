-- C1X (pattern 3). Reference query.
SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
JOIN dim_date d ON d.calendar_date = f.sale_date
WHERE s.store_id = 108 AND p.subcategory = 'Interior Paint' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3;

-- Sloppy variant 1 (must give the reference result)
SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store cs ON cs.store_key = f.store_key AND cs.store_id = 108
JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
WHERE cp.subcategory = 'Interior Paint' AND f.sale_date BETWEEN DATE '2026-06-29' AND DATE '2026-08-02';
