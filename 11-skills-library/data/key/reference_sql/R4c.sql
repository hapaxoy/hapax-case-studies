-- R4c (pattern 4). Reference query.
WITH sold AS (
    SELECT s.format AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 
    GROUP BY 1
),
returned AS (
    SELECT s.format AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 
    GROUP BY 1
)
SELECT sold.grp AS format, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;

-- Also accepted: stores only (three rows, no Web row), since store-level analyses cover the physical stores
WITH sold AS (
    SELECT s.format AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 AND s.store_id < 900
    GROUP BY 1
),
returned AS (
    SELECT s.format AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 AND s.store_id < 900
    GROUP BY 1
)
SELECT sold.grp AS format, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;

-- Also accepted: web sales placed in the cohort by their dispatch date instead of their order date
WITH web_dispatch AS (
    SELECT web_order_id, CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
lines AS (
    SELECT f.sales_line_id, s.format, f.net_amount, COALESCE(w.dispatch_date, f.sale_date) AS cohort_date
    FROM fact_sales_line f JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
in_cohort AS (SELECT l.* FROM lines l JOIN dim_date d ON d.calendar_date = l.cohort_date WHERE d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2),
sold AS (SELECT format, SUM(net_amount) AS sold_net FROM in_cohort GROUP BY 1),
returned AS (SELECT c.format, SUM(r.refund_net) AS returned_net FROM fact_return_line r JOIN in_cohort c ON c.sales_line_id = r.sales_line_id GROUP BY 1)
SELECT sold.format, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (format) ORDER BY 1;

-- Naive variant [company_definition] return_date_convention: Counts refunds in the period they were paid and divides by sales in the same period, so refunds for goods bought before the period land in it and refunds still to come are missed.
WITH sold AS (
    SELECT s.format AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 
    GROUP BY 1
),
returned AS (
    -- returns counted in the period they were booked
    SELECT s.format AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = r.return_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_period = 2 
    GROUP BY 1
)
SELECT sold.grp AS format, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;
