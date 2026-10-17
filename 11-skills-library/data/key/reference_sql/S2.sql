-- S2 (pattern 10). Reference query.
WITH stock AS (
    SELECT cp.category, SUM(w.closing_units) AS closing_units
    FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE w.week_ending_date = DATE '2026-09-27' GROUP BY 1
),
sold AS (
    SELECT cp.category, SUM(f.quantity) / 4.0 AS avg_weekly_units
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE f.sale_date BETWEEN DATE '2026-08-24' AND DATE '2026-09-20' AND s.store_id < 900
    GROUP BY 1
)
SELECT stock.category, ROUND(stock.closing_units / sold.avg_weekly_units, 2) AS weeks_of_cover
FROM stock JOIN sold USING (category) ORDER BY 1;

-- Also accepted: web units counted in the denominator
WITH stock AS (
    SELECT cp.category, SUM(w.closing_units) AS closing_units
    FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE w.week_ending_date = DATE '2026-09-27' GROUP BY 1
),
sold AS (
    SELECT cp.category, SUM(f.quantity) / 4.0 AS avg_weekly_units
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE f.sale_date BETWEEN DATE '2026-08-24' AND DATE '2026-09-20' AND s.store_id <> 999
    GROUP BY 1
)
SELECT stock.category, ROUND(stock.closing_units / sold.avg_weekly_units, 2) AS weeks_of_cover
FROM stock JOIN sold USING (category) ORDER BY 1;

-- Also accepted: the four weeks ending at the stock week (18 to 21) in the denominator
WITH stock AS (
    SELECT cp.category, SUM(w.closing_units) AS closing_units
    FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE w.week_ending_date = DATE '2026-09-27' GROUP BY 1
),
sold AS (
    SELECT cp.category, SUM(f.quantity) / 4.0 AS avg_weekly_units
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE f.sale_date BETWEEN DATE '2026-08-31' AND DATE '2026-09-27' AND s.store_id < 900
    GROUP BY 1
)
SELECT stock.category, ROUND(stock.closing_units / sold.avg_weekly_units, 2) AS weeks_of_cover
FROM stock JOIN sold USING (category) ORDER BY 1;

-- Naive variant [semi_additive] stock_added_across_weeks: Adds the closing stock of the last four weeks together before dividing, which counts the same stock four times.
WITH stock AS (
    SELECT cp.category, SUM(w.closing_units) AS closing_units
    FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE w.week_ending_date BETWEEN DATE '2026-09-06' AND DATE '2026-09-27' GROUP BY 1
),
sold AS (
    SELECT cp.category, SUM(f.quantity) / 4.0 AS avg_weekly_units
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    WHERE f.sale_date BETWEEN DATE '2026-08-24' AND DATE '2026-09-20' AND s.store_id < 900
    GROUP BY 1
)
SELECT stock.category, ROUND(stock.closing_units / sold.avg_weekly_units, 2) AS weeks_of_cover
FROM stock JOIN sold USING (category) ORDER BY 1;
