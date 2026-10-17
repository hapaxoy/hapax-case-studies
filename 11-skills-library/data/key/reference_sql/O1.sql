-- O1 (pattern 1). Reference query.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.region AS region, f.gross_amount AS gross
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT region,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN gross ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN gross ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM lines WHERE business_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30'
GROUP BY 1 ORDER BY 1;

-- Naive variant [override] as_is_region_default: Uses today's regions (the company default) although the request asks for the regions as they were. The Capital Region appears and South is too small.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, (SELECT cs.region FROM dim_store cs WHERE cs.store_id = s.store_id AND cs.is_current) AS region, f.gross_amount AS gross
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT region,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN gross ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN gross ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM lines WHERE business_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30'
GROUP BY 1 ORDER BY 1;

-- Naive variant [vat] flat_vat_rate: Multiplies net sales by one flat 25.5% VAT rate. August 2024 was at 24%, and reduced-rate goods carry 14% or 10%.
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, s.region AS region, f.net_amount * 1.255 AS gross
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
)
SELECT region,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-08-01' AND DATE '2024-08-31' THEN gross ELSE 0 END), 2) AS gross_incl_vat_aug_2024,
       ROUND(SUM(CASE WHEN business_date BETWEEN DATE '2024-09-01' AND DATE '2024-09-30' THEN gross ELSE 0 END), 2) AS gross_incl_vat_sep_2024
FROM lines WHERE business_date BETWEEN DATE '2024-08-01' AND DATE '2024-09-30'
GROUP BY 1 ORDER BY 1;
