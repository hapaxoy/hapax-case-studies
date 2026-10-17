-- Weeks of cover by store and category (as-is) at the end of one fiscal week.
-- facts: DEF-WEEKS-COVER, DEF-STOCK-SEMIADD, REG-STOCK-SNAPSHOT, DEF-STORE-SCOPE, REG-TEST-SKU, DEF-HIERARCHY-ASIS
-- Weeks of cover = closing stock units at the end of the fiscal week / average weekly units sold over the
-- prior four fiscal weeks, for the same store or grouping. Units sold = quantity on sales lines, by sale date.
-- This template reads "prior four fiscal weeks" as the four weeks before the snapshot week
-- (week_ending - 34 days to week_ending - 7 days).
-- Grain of the output: store_id x category. For a store total, drop category from both CTEs.
WITH params AS (
    SELECT DATE '2026-09-27' AS week_ending          -- a Sunday: end of FY2026/27 P05
),
closing AS (
    SELECT cs.store_id, cp.category, SUM(fs.closing_units) AS closing_units
    FROM fact_stock_week fs
    JOIN dim_store s    ON s.store_key = fs.store_key
    JOIN dim_store cs   ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p  ON p.product_key = fs.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    CROSS JOIN params
    WHERE fs.week_ending_date = params.week_ending
      AND s.store_id < 900 AND p.category <> 'ZZ Test'
    GROUP BY 1, 2
),
sold AS (
    SELECT cs.store_id, cp.category, SUM(f.quantity) AS units_sold_4w
    FROM fact_sales_line f
    JOIN dim_store s    ON s.store_key = f.store_key
    JOIN dim_store cs   ON cs.store_id = s.store_id AND cs.is_current
    JOIN dim_product p  ON p.product_key = f.product_key
    JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
    CROSS JOIN params
    WHERE f.sale_date BETWEEN params.week_ending - 34 AND params.week_ending - 7
      AND s.store_id < 900 AND p.category <> 'ZZ Test'
    GROUP BY 1, 2
)
SELECT c.store_id, c.category, c.closing_units,
       ROUND(COALESCE(s.units_sold_4w, 0) / 4.0, 1) AS avg_weekly_units_sold,
       CASE WHEN COALESCE(s.units_sold_4w, 0) = 0 THEN NULL
            ELSE ROUND(c.closing_units / (s.units_sold_4w / 4.0), 1) END AS weeks_of_cover
FROM closing c
LEFT JOIN sold s ON s.store_id = c.store_id AND s.category = c.category
ORDER BY c.store_id, c.category;
