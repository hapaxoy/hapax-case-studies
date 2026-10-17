-- V2 (pattern 14). Reference query.
SELECT ROUND(f.vat_rate * 100, 1) AS vat_rate_pct, ROUND(SUM(f.gross_amount - f.net_amount), 2) AS vat_amount
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test' AND f.sale_date BETWEEN DATE '2024-08-26' AND DATE '2024-09-22'
GROUP BY 1 ORDER BY 1;

-- Naive variant [vat] flat_25_5: Applies 25.5% to all net sales, one row instead of four. It ignores the 24% days and the reduced-rate goods.
SELECT 25.5 AS vat_rate_pct, ROUND(SUM(f.net_amount) * 0.255, 2) AS vat_amount
FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
WHERE s.store_id < 900 AND p.category <> 'ZZ Test' AND f.sale_date BETWEEN DATE '2024-08-26' AND DATE '2024-09-22';
