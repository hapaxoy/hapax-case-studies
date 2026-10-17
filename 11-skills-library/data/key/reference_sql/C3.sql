-- C3 (pattern 3). Reference query.
SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id = 131 AND p.sku = 101624 AND f.sale_date BETWEEN DATE '2026-09-28' AND DATE '2026-10-04';

-- Sloppy variant 1 (must give the reference result)
SELECT SUM(f.quantity) AS units_sold
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product cp ON cp.sku = 101624 AND cp.is_current
WHERE s.store_id = 131 AND f.product_key IN (SELECT product_key FROM dim_product WHERE sku = 101624)
  AND f.sale_date >= DATE '2026-09-28' AND f.sale_date <= DATE '2026-10-04' AND s.store_id < 999;
