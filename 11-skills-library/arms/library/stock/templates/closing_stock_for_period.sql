-- Closing stock for a fiscal range by store: average of the weekly closings and the last week's closing.
-- facts: DEF-STOCK-SEMIADD, REG-STOCK-SNAPSHOT, DEF-STORE-SCOPE, REG-TEST-SKU, REG-SCD-KEYS
-- Closing stock is a snapshot at the end of each fiscal week (week-ending Sunday). Add it across stores
-- and products, never across weeks: first sum within each week, then average the weeks or take the last.
-- Rows exist only for articles the store ranges. Web orders are picked from the central warehouse,
-- which is not in this table, so there is no web stock here.
-- Grain of the output: store_id.
WITH params AS (
    SELECT DATE '2026-08-31' AS start_date, DATE '2026-09-27' AS end_date      -- FY2026/27 P05, weeks end on Sundays
),
weekly AS (
    -- step 1: add across products within each store-week
    SELECT fs.week_ending_date, cs.store_id, cs.store_name,
           SUM(fs.closing_units) AS closing_units, SUM(fs.closing_value) AS closing_value
    FROM fact_stock_week fs
    JOIN dim_store s    ON s.store_key = fs.store_key
    JOIN dim_store cs   ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p  ON p.product_key = fs.product_key
    CROSS JOIN params
    WHERE fs.week_ending_date BETWEEN params.start_date AND params.end_date
      AND s.store_id < 900 AND p.category <> 'ZZ Test'
    GROUP BY 1, 2, 3
)
-- step 2: across weeks, average or take the last week - never sum
SELECT store_id, store_name,
       COUNT(*) AS weeks,
       ROUND(AVG(closing_units), 1) AS avg_weekly_closing_units,
       ROUND(AVG(closing_value), 2) AS avg_weekly_closing_value,
       arg_max(closing_units, week_ending_date) AS last_week_closing_units,
       arg_max(closing_value, week_ending_date) AS last_week_closing_value,
       MAX(week_ending_date) AS last_week_ending
FROM weekly
GROUP BY 1, 2
ORDER BY 1;
