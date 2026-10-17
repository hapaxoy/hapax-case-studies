-- U3 (pattern 10). Reference query.
WITH weekly AS (
    SELECT cp.category, w.week_ending_date, SUM(w.closing_value) AS v
    FROM (SELECT * FROM fact_stock_week QUALIFY row_number() OVER (PARTITION BY store_key, product_key, week_ending_date ORDER BY etl_loaded_at) = 1) w
    JOIN dim_store s ON s.store_key = w.store_key JOIN dim_store cs ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d ON d.calendar_date = w.week_ending_date
    WHERE cs.region = 'West' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
    GROUP BY 1, 2
)
SELECT category, ROUND(AVG(v), 2) AS average_stock_value FROM weekly GROUP BY 1 ORDER BY 1;

-- Published number (same question without the repair; the problem is in no document)
WITH weekly AS (
    SELECT cp.category, w.week_ending_date, SUM(w.closing_value) AS v
    FROM fact_stock_week w
    JOIN dim_store s ON s.store_key = w.store_key JOIN dim_store cs ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d ON d.calendar_date = w.week_ending_date
    WHERE cs.region = 'West' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
    GROUP BY 1, 2
)
SELECT category, ROUND(AVG(v), 2) AS average_stock_value FROM weekly GROUP BY 1 ORDER BY 1;

-- Naive variant [semi_additive] sum_of_weekly_snapshots: Adds the four weekly snapshots together instead of averaging them, which counts the same stock four times.
WITH weekly AS (
    SELECT cp.category, w.week_ending_date, SUM(w.closing_value) AS v
    FROM (SELECT * FROM fact_stock_week QUALIFY row_number() OVER (PARTITION BY store_key, product_key, week_ending_date ORDER BY etl_loaded_at) = 1) w
    JOIN dim_store s ON s.store_key = w.store_key JOIN dim_store cs ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    JOIN dim_date d ON d.calendar_date = w.week_ending_date
    WHERE cs.region = 'West' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 11
    GROUP BY 1, 2
)
SELECT category, ROUND(SUM(v), 2) AS average_stock_value FROM weekly GROUP BY 1 ORDER BY 1;
