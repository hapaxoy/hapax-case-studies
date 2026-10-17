-- R4b (pattern 4). Reference query.
WITH sold AS (
    SELECT cp.subcategory AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden'
    GROUP BY 1
),
returned AS (
    SELECT cp.subcategory AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden'
    GROUP BY 1
)
SELECT sold.grp AS subcategory, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;

-- Also accepted: the whole Outdoor Lighting subcategory counted in Electrical, so it is not a Garden row at all
WITH sold AS (
    SELECT cp.subcategory AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden' AND cp.subcategory <> 'Outdoor Lighting'
    GROUP BY 1
),
returned AS (
    SELECT cp.subcategory AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden' AND cp.subcategory <> 'Outdoor Lighting'
    GROUP BY 1
)
SELECT sold.grp AS subcategory, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;

-- Naive variant [company_definition] return_date_convention: Counts refunds in the period they were paid and divides by the sales of the same period, the net-sales convention, instead of matching refunds to the sale period.
WITH sold AS (
    SELECT cp.subcategory AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden'
    GROUP BY 1
),
returned AS (
    -- returns counted in the period they were booked
    SELECT cp.subcategory AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key JOIN dim_product cp ON cp.sku = p.sku AND cp.is_current 
    JOIN dim_date d ON d.calendar_date = r.return_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND cp.category = 'Garden'
    GROUP BY 1
)
SELECT sold.grp AS subcategory, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;

-- Naive variant [scd] as_was_category: Uses the category the article had on the day of sale, so the outdoor lighting range still appears as a Garden subcategory.
WITH sold AS (
    SELECT p.subcategory AS grp, SUM(f.net_amount) AS sold_net
    FROM fact_sales_line f
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND p.category = 'Garden'
    GROUP BY 1
),
returned AS (
    SELECT p.subcategory AS grp, SUM(r.refund_net) AS returned_net
    FROM fact_return_line r
    JOIN fact_sales_line f ON f.sales_line_id = r.sales_line_id
    JOIN dim_store s ON s.store_key = f.store_key JOIN dim_product p ON p.product_key = f.product_key  
    JOIN dim_date d ON d.calendar_date = f.sale_date
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test' AND d.fiscal_year = 'FY2025/26' AND d.fiscal_quarter = 1 AND p.category = 'Garden'
    GROUP BY 1
)
SELECT sold.grp AS subcategory, ROUND(sold.sold_net, 2) AS sold_net, ROUND(COALESCE(returned.returned_net, 0), 2) AS returned_net,
       ROUND(100.0 * COALESCE(returned.returned_net, 0) / sold.sold_net, 2) AS return_rate_pct
FROM sold LEFT JOIN returned USING (grp) ORDER BY 1;
