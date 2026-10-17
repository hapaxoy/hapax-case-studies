-- Net sales by category both ways: as-is (current product version) and as-was (version on the date).
-- facts: DEF-HIERARCHY-ASIS, TEAM-ASIS, REG-OUTDOOR-LIGHTING, REG-SCD-KEYS, DEF-NET-SALES
-- Use it to show a requester how much a restatement moves, e.g. the outdoor lighting move from Garden
-- to Electrical from 27 October 2025 (REQ-D11 reported FY2024/25 as-is, outdoor lighting in Electrical).
-- Both columns add up to the same total; only the split between categories changes.
-- Grain of the output: category.
WITH params AS (
    SELECT 'FY2024/25' AS fiscal_year
),
web_dispatch AS (
    SELECT web_order_id,
           CAST(timezone('Europe/Helsinki', dispatch_ts_utc AT TIME ZONE 'UTC') AS DATE) AS dispatch_date
    FROM fact_web_order
    WHERE status IN ('delivered', 'collected')
),
net_lines AS (
    SELECT COALESCE(w.dispatch_date, f.sale_date) AS business_date, p.sku, p.category AS category_as_was,
           f.net_amount AS net_sales
    FROM fact_sales_line f
    JOIN dim_store s   ON s.store_key = f.store_key
    JOIN dim_product p ON p.product_key = f.product_key
    LEFT JOIN web_dispatch w ON w.web_order_id = f.receipt_id
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
    UNION ALL
    SELECT r.return_date, p.sku, p.category, -r.refund_net
    FROM fact_return_line r
    JOIN dim_store s   ON s.store_key = r.store_key
    JOIN dim_product p ON p.product_key = r.product_key
    WHERE s.store_id <> 999 AND p.category <> 'ZZ Test'
),
dated AS (
    SELECT n.*, cp.category AS category_as_is
    FROM net_lines n
    JOIN dim_date d     ON d.calendar_date = n.business_date
    JOIN dim_product cp ON cp.sku = n.sku AND cp.is_current
    CROSS JOIN params
    WHERE d.fiscal_year = params.fiscal_year
),
as_is AS (SELECT category_as_is AS category, SUM(net_sales) AS net_sales FROM dated GROUP BY 1),
as_was AS (SELECT category_as_was AS category, SUM(net_sales) AS net_sales FROM dated GROUP BY 1)
SELECT COALESCE(i.category, w.category) AS category,
       i.net_sales AS net_sales_as_is, w.net_sales AS net_sales_as_was,
       COALESCE(i.net_sales, 0) - COALESCE(w.net_sales, 0) AS restatement
FROM as_is i FULL JOIN as_was w ON w.category = i.category
ORDER BY 1;
