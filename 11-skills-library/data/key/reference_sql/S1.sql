-- S1 (pattern 10). Reference query.
SELECT ROUND(AVG(weekly), 2) AS average_stock_value FROM (SELECT w.week_ending_date, SUM(w.closing_value) AS weekly FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date
WHERE cp.category = 'Paint & Decorating' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3 GROUP BY 1);

-- Naive variant [semi_additive] sum_of_weekly_snapshots: Adds the five weekly snapshots together, which counts the same stock five times.
SELECT ROUND(SUM(w.closing_value), 2) AS average_stock_value FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date
WHERE cp.category = 'Paint & Decorating' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3;

-- Naive variant [semi_additive] average_of_rows: Averages the stock value of each product-store line instead of the total held, which gives the typical value of one line, not the stock.
SELECT ROUND(AVG(w.closing_value), 2) AS average_stock_value FROM fact_stock_week w JOIN dim_product p ON p.product_key = w.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current
JOIN dim_date d ON d.calendar_date = w.week_ending_date
WHERE cp.category = 'Paint & Decorating' AND d.fiscal_year = 'FY2026/27' AND d.fiscal_period = 3;
