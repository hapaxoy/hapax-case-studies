-- V1 (pattern 14). Reference query.
SELECT ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN f.gross_amount ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN f.gross_amount ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test' AND f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30';

-- Naive variant [vat] flat_25_5: Multiplies net sales by 25.5% for both months. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%.
SELECT ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN f.net_amount * 1.255 ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN f.net_amount * 1.255 ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test' AND f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30';

-- Naive variant [vat] flat_24: Multiplies net sales by 24% for both months. September 2024 was at 25.5%.
SELECT ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN f.net_amount * 1.24 ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN f.sale_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN f.net_amount * 1.24 ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test' AND f.sale_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30';
