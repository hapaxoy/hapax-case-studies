-- C12 (pattern 4). Reference query.
SELECT SUM(r.quantity_returned) AS units_returned
FROM fact_return_line r JOIN dim_product p ON p.product_key = r.product_key
JOIN dim_date d ON d.calendar_date = r.return_date
WHERE p.subcategory = 'Garden Furniture' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 4;

-- Sloppy variant 1 (must give the reference result)
SELECT SUM(r.quantity_returned) AS units_returned
FROM fact_return_line r JOIN dim_product p ON p.product_key = r.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
WHERE cp.subcategory = 'Garden Furniture' AND r.return_date BETWEEN DATE '2026-08-03' AND DATE '2026-08-30' AND r.store_key NOT IN (SELECT store_key FROM dim_store WHERE store_id = 999);
